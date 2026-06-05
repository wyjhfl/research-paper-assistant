from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Idea, IdeaSource
from ..repositories.idea_repo import IdeaRepository
from ..repositories.paper_repo import PaperRepository
from ..services.rag_service import RAGService
from ..services.multi_paper_rag_service import MultiPaperRAGService
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
        extraction_method: str = "heuristic",
    ):
        self.title = title
        self.summary = summary
        self.research_question = research_question
        self.method_hint = method_hint
        self.tags = tags
        self.source_chunk_ids = source_chunk_ids
        self.confidence = confidence
        self.extraction_method = extraction_method


@dataclass
class ExtractIdeasResult:
    candidates: list[IdeaCandidate]
    reason: str = ""
    suggestions: list[str] = field(default_factory=list)
    extraction_method: str = ""


@dataclass
class CrossPaperIdea:
    title: str
    summary: str
    motivation: str
    involved_paper_ids: list[int]
    confidence: float
    extraction_method: str = "cross_paper_synthesis"


class IdeaService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.idea_repo = IdeaRepository(session)
        self.paper_repo = PaperRepository(session)

    async def extract_ideas(
        self,
        paper_id: int,
        user_id: str = "default",
        use_llm_fallback: bool = True,
        max_ideas: int = 3,
    ) -> ExtractIdeasResult:
        paper = await self.paper_repo.get_paper(paper_id, user_id=user_id)
        if paper is None:
            raise ValueError(f"Paper {paper_id} not found for user {user_id}")

        if paper.status != "completed":
            raise ValueError(f"Paper {paper_id} is not ready (status={paper.status})")

        chunks = await self.paper_repo.get_chunks_by_paper(paper_id)
        if not chunks:
            return ExtractIdeasResult(
                candidates=[],
                reason="未检测到明确 limitation/future work/open problem",
                suggestions=[
                    "上传完整论文以获取更多上下文",
                    "尝试跨论文 idea 合成",
                    "后续接入真实 embedding 提升检索质量",
                ],
                extraction_method="",
            )

        # Step 1: Try heuristic extraction first
        heuristic_candidates = self._heuristic_ideas(chunks, paper.title)
        if heuristic_candidates:
            return ExtractIdeasResult(
                candidates=heuristic_candidates[:max_ideas],
                reason="",
                suggestions=[],
                extraction_method="heuristic",
            )

        # Step 2: Heuristic returned 0 — try LLM fallback if enabled
        if not use_llm_fallback:
            return ExtractIdeasResult(
                candidates=[],
                reason="未检测到明确 limitation/future work/open problem",
                suggestions=[
                    "上传完整论文以获取更多上下文",
                    "开启 LLM fallback (use_llm_fallback=true)",
                    "尝试跨论文 idea 合成",
                    "后续接入真实 embedding 提升检索质量",
                ],
                extraction_method="heuristic",
            )

        # Step 3: LLM fallback
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

        llm_start = time.monotonic()
        raw = None
        try:
            llm = get_llm_provider()
            prompt = (
                f"Based on the following contexts from the paper '{paper.title}', "
                f"extract {max_ideas} research ideas as JSON array. Each idea should have: "
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
            duration_ms = int((time.monotonic() - llm_start) * 1000) if raw is None else 0
            await record_model_call(
                user_id=user_id,
                operation="llm_idea_extract",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="failed",
                duration_ms=duration_ms,
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=0,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={"paper_id": paper_id},
            )
            logger.exception("LLM provider failed for idea extraction on paper %d", paper_id)
            raw = None

        candidates: list[IdeaCandidate] = []
        if raw:
            candidates = self._parse_ideas(raw, extraction_method="llm_fallback")

        if not candidates:
            return ExtractIdeasResult(
                candidates=[],
                reason="LLM fallback 解析失败，未生成有效 idea" if raw else "LLM fallback 不可用",
                suggestions=[
                    "上传完整论文以获取更多上下文",
                    "尝试跨论文 idea 合成",
                    "后续接入真实 embedding 提升检索质量",
                ],
                extraction_method="llm_fallback" if raw else "heuristic",
            )

        for c in candidates:
            c.source_chunk_ids = [chunks[0].id] if chunks else []

        candidates = candidates[:max_ideas]

        return ExtractIdeasResult(
            candidates=candidates,
            reason="",
            suggestions=[],
            extraction_method="llm_fallback",
        )

    async def synthesize_ideas(
        self,
        paper_ids: list[int],
        user_id: str = "default",
        max_ideas: int = 3,
    ) -> list[CrossPaperIdea]:
        rag = MultiPaperRAGService(self.session, user_id=user_id)

        paper_titles: dict[int, str] = {}
        for pid in paper_ids:
            paper = await self.paper_repo.get_paper(pid, user_id=user_id)
            if paper is not None:
                paper_titles[pid] = paper.title

        query = "What are the key research limitations, future directions, and open problems across these papers?"
        try:
            search_results = await rag.search(query=query, paper_ids=paper_ids, top_k=10)
        except Exception:
            logger.exception("Multi-paper search failed for idea synthesis")
            search_results = []

        if not search_results:
            logger.info("No search results for idea synthesis across papers %s", paper_ids)
            return []

        contexts = [r.text_excerpt for r in search_results[:8]]
        paper_summary = "\n".join(f"- Paper {pid}: {paper_titles.get(pid, 'Unknown')}" for pid in paper_ids)

        prompt = (
            f"Based on the following contexts from multiple papers, "
            f"identify {max_ideas} cross-paper research directions that combine insights from multiple papers. "
            f"Each idea should have: title, summary, motivation (why this direction matters), "
            f"involved_paper_ids (list of paper IDs), confidence (0-1).\n\n"
            f"Papers:\n{paper_summary}\n\n"
            f"Contexts:\n" + "\n---\n".join(contexts)
        )

        llm_start = time.monotonic()
        try:
            llm = get_llm_provider()
            llm_start = time.monotonic()
            raw = await llm.generate_answer(prompt, contexts)
            await record_model_call(
                user_id=user_id,
                operation="llm_idea_synthesis",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="success",
                duration_ms=int((time.monotonic() - llm_start) * 1000),
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=len(raw),
                metadata={"paper_ids": paper_ids, "idea_count": 0},
            )
        except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError) as exc:
            duration_ms = int((time.monotonic() - llm_start) * 1000)
            await record_model_call(
                user_id=user_id,
                operation="llm_idea_synthesis",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="failed",
                duration_ms=duration_ms,
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=0,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={"paper_ids": paper_ids},
            )
            logger.exception("LLM provider failed for idea synthesis")
            return []

        return self._parse_cross_paper_ideas(raw, paper_ids, max_ideas)

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

    def _parse_ideas(self, raw: str, extraction_method: str = "llm_fallback") -> list[IdeaCandidate]:
        candidates = []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("ideas", [])
            else:
                return []
            if not isinstance(items, list):
                return []
            for item in items[:5]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()[:120]
                if not title:
                    continue
                # Clean tags: must be list[str], exclude bool (subclass of int)
                raw_tags = item.get("tags", [])
                if not isinstance(raw_tags, list):
                    raw_tags = []
                tags = [str(t) for t in raw_tags if isinstance(t, str) or (isinstance(t, (int, float)) and not isinstance(t, bool))][:5]
                # Clamp confidence to [0, 1]
                try:
                    confidence = float(item.get("confidence", 0.5))
                    confidence = max(0.0, min(1.0, confidence))
                except (TypeError, ValueError):
                    confidence = 0.5
                candidates.append(IdeaCandidate(
                    title=title,
                    summary=str(item.get("summary", ""))[:500],
                    research_question=str(item.get("research_question", ""))[:300],
                    method_hint=str(item.get("method_hint", ""))[:300],
                    tags=tags,
                    source_chunk_ids=[],
                    confidence=confidence,
                    extraction_method=extraction_method,
                ))
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Failed to parse LLM idea output as JSON, returning empty")
        return candidates

    # Keywords indicating research idea clues in chunk text
    _IDEA_CLUE_PATTERNS: list[str] = [
        "limitation", "future work", "open problem", "challenge",
        "propose", "improve", "extend", "direction",
        "局限", "未来工作", "挑战", "改进", "扩展", "研究方向",
    ]

    def _heuristic_ideas(self, chunks: list, paper_title: str) -> list[IdeaCandidate]:
        """Conservative heuristic: only return ideas when text contains explicit
        research clue keywords. Generic/ordinary chunks return empty."""
        if not chunks:
            return []

        # Scan all chunks for idea clues
        matched_chunks: list[tuple[int, str]] = []  # (chunk_index, matched_keyword)
        for i, chunk in enumerate(chunks):
            text_lower = chunk.text[:1200].lower()
            for kw in self._IDEA_CLUE_PATTERNS:
                if kw in text_lower:
                    matched_chunks.append((i, kw))
                    break  # One match per chunk is enough

        if not matched_chunks:
            return []

        # Build candidates from matched chunks (up to 3)
        candidates: list[IdeaCandidate] = []
        for chunk_idx, keyword in matched_chunks[:3]:
            chunk = chunks[chunk_idx]
            text = chunk.text[:800]
            # Extract a short excerpt around the keyword
            kw_pos = text.lower().find(keyword)
            if kw_pos >= 0:
                start = max(0, kw_pos - 80)
                end = min(len(text), kw_pos + len(keyword) + 120)
                excerpt = text[start:end].strip()
            else:
                excerpt = text[:200].strip()

            candidates.append(IdeaCandidate(
                title=f"Research direction from {paper_title[:60]}",
                summary=excerpt[:300],
                research_question=f"What are the implications of '{keyword}' mentioned in this paper?",
                method_hint="Literature analysis and synthesis",
                tags=["auto-extracted", keyword.replace(" ", "-")],
                source_chunk_ids=[chunk.id],
                confidence=0.4,
                extraction_method="heuristic",
            ))

        return candidates

    def _parse_cross_paper_ideas(
        self, raw: str, paper_ids: list[int], max_ideas: int,
    ) -> list[CrossPaperIdea]:
        ideas: list[CrossPaperIdea] = []
        try:
            data = json.loads(raw)
            items = data if isinstance(data, list) else data.get("ideas", [])
            if not isinstance(items, list):
                return []
            for item in items[:max_ideas]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()[:120]
                if not title:
                    continue
                involved = item.get("involved_paper_ids", [])
                if not isinstance(involved, list):
                    involved = []
                involved = [int(pid) for pid in involved if isinstance(pid, (int, float)) and int(pid) in paper_ids]
                if not involved:
                    involved = paper_ids[:2]
                try:
                    confidence = float(item.get("confidence", 0.5))
                    confidence = max(0.0, min(1.0, confidence))
                except (TypeError, ValueError):
                    confidence = 0.5
                ideas.append(CrossPaperIdea(
                    title=title,
                    summary=str(item.get("summary", ""))[:500],
                    motivation=str(item.get("motivation", ""))[:500],
                    involved_paper_ids=involved,
                    confidence=confidence,
                    extraction_method="cross_paper_synthesis",
                ))
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Failed to parse cross-paper LLM idea output")
        return ideas
