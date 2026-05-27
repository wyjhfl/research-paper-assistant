from __future__ import annotations

import json
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Idea, IdeaSource
from ..repositories.idea_repo import IdeaRepository
from ..repositories.paper_repo import PaperRepository
from ..services.rag_service import RAGService
from ..services.ai_provider import get_llm_provider, ProviderConfigurationError, ProviderRequestError, ProviderResponseError
from .model_call_audit_service import record_model_call

logger = logging.getLogger(__name__)


class DuplicateIdeaError(Exception):
    pass


class InvalidChunkIdsError(Exception):
    pass


class IdeaCandidate:
    def __init__(
        self,
        title: str,
        summary: str,
        research_question: str,
        method_hint: str,
        tags: list[str],
        source_chunk_ids: list[int],
        confidence: float,
    ):
        self.title = title
        self.summary = summary
        self.research_question = research_question
        self.method_hint = method_hint
        self.tags = tags
        self.source_chunk_ids = source_chunk_ids
        self.confidence = confidence


class IdeaService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.idea_repo = IdeaRepository(session)
        self.paper_repo = PaperRepository(session)

    async def extract_ideas(
        self, paper_id: int, user_id: str = "default"
    ) -> list[IdeaCandidate]:
        paper = await self.paper_repo.get_paper(paper_id, user_id=user_id)
        if paper is None:
            raise ValueError(f"Paper {paper_id} not found for user {user_id}")

        if paper.status != "completed":
            raise ValueError(f"Paper {paper_id} is not ready (status={paper.status})")

        chunks = await self.paper_repo.get_chunks_by_paper(paper_id)
        if not chunks:
            return []

        rag = RAGService(self.session, user_id=user_id)
        try:
            result = await rag.ask(paper_id, "What are the key research ideas and future directions in this paper?")
        except Exception:
            logger.exception("RAG failed for idea extraction on paper %d", paper_id)
            result = None

        contexts = []
        if result and result.sources:
            contexts = [s.text_excerpt for s in result.sources[:3]]
        else:
            contexts = [chunks[0].text[:500]] if chunks else []

        try:
            llm = get_llm_provider()
            prompt = (
                f"Based on the following contexts from the paper '{paper.title}', "
                f"extract 3-5 research ideas as JSON array. Each idea should have: "
                f"title, summary, research_question, method_hint, tags (list), confidence (0-1).\n\n"
                f"Contexts:\n" + "\n---\n".join(contexts)
            )
            llm_start = time.monotonic()
            raw = await llm.generate_answer(prompt, contexts)
            await record_model_call(
                user_id=user_id,
                operation="llm_idea_extract",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="success",
                duration_ms=int((time.monotonic() - llm_start) * 1000),
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=len(raw),
                metadata={"paper_id": paper_id, "idea_count": 0},
            )
        except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError) as exc:
            await record_model_call(
                user_id=user_id,
                operation="llm_idea_extract",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="failed",
                duration_ms=int((time.monotonic() - llm_start) * 1000),
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=0,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={"paper_id": paper_id},
            )
            logger.exception("LLM provider failed for idea extraction on paper %d", paper_id)
            raw = None

        if raw:
            candidates = self._parse_ideas(raw)
        else:
            candidates = self._heuristic_ideas(chunks, paper.title)

        for c in candidates:
            c.source_chunk_ids = [chunks[0].id] if chunks else []

        return candidates

    async def save_idea(
        self,
        paper_id: int,
        title: str,
        summary: str,
        research_question: str,
        method_hint: str,
        tags: list[str],
        source_chunk_ids: list[int],
        confidence: float = 0.5,
        user_id: str = "default",
    ) -> Idea:
        existing = await self.idea_repo.get_idea_by_title_and_paper(
            paper_id, title, user_id=user_id
        )
        if existing is not None:
            raise DuplicateIdeaError(f"Idea '{title}' already exists for paper {paper_id}")

        paper = await self.paper_repo.get_paper(paper_id, user_id=user_id)
        if paper is None:
            raise ValueError(f"Paper {paper_id} not found for user {user_id}")

        chunks = await self.paper_repo.get_chunks_by_paper(paper_id)
        chunk_ids = {c.id for c in chunks}
        for cid in source_chunk_ids:
            if cid not in chunk_ids:
                raise InvalidChunkIdsError(f"Chunk {cid} does not belong to paper {paper_id}")

        idea = Idea(
            paper_id=paper_id,
            title=title,
            summary=summary,
            research_question=research_question,
            method_hint=method_hint,
            tags=json.dumps(tags, ensure_ascii=False),
            confidence=confidence,
            status="saved",
            user_id=user_id,
        )
        idea = await self.idea_repo.create_idea(idea)

        for cid in source_chunk_ids:
            chunk = next(c for c in chunks if c.id == cid)
            source = IdeaSource(
                idea_id=idea.id,
                paper_id=paper_id,
                chunk_id=cid,
                chunk_index=chunk.chunk_index,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                text_excerpt=chunk.text[:200],
            )
            await self.idea_repo.create_idea_source(source)

        await self.session.flush()
        return idea

    async def list_ideas(self, user_id: str = "default") -> list[Idea]:
        return await self.idea_repo.list_ideas(user_id=user_id)

    async def get_idea(self, idea_id: int, user_id: str = "default") -> Idea | None:
        return await self.idea_repo.get_idea(idea_id, user_id=user_id)

    async def delete_idea(self, idea_id: int, user_id: str = "default") -> bool:
        return await self.idea_repo.delete_idea(idea_id, user_id=user_id)

    def _parse_ideas(self, raw: str) -> list[IdeaCandidate]:
        candidates = []
        try:
            data = json.loads(raw)
            items = data if isinstance(data, list) else data.get("ideas", [])
            for item in items[:5]:
                candidates.append(IdeaCandidate(
                    title=str(item.get("title", ""))[:120],
                    summary=str(item.get("summary", ""))[:500],
                    research_question=str(item.get("research_question", ""))[:300],
                    method_hint=str(item.get("method_hint", ""))[:300],
                    tags=item.get("tags", [])[:5],
                    source_chunk_ids=[],
                    confidence=float(item.get("confidence", 0.5)),
                ))
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Failed to parse LLM idea output, using heuristic fallback")
            candidates = [IdeaCandidate(
                title="Research Direction (auto-extracted)",
                summary=raw[:300],
                research_question="TBD",
                method_hint="TBD",
                tags=["auto-extracted"],
                source_chunk_ids=[],
                confidence=0.3,
            )]
        return candidates

    def _heuristic_ideas(self, chunks: list, paper_title: str) -> list[IdeaCandidate]:
        if not chunks:
            return []
        text = chunks[0].text[:800]
        return [IdeaCandidate(
            title=f"Research direction from {paper_title[:60]}",
            summary=text[:300],
            research_question="What are the key findings and future directions?",
            method_hint="Literature analysis and synthesis",
            tags=["auto-extracted"],
            source_chunk_ids=[],
            confidence=0.3,
        )]
