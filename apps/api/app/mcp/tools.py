from __future__ import annotations

import json
import logging
from typing import Any

from ..database import async_session as _default_session_factory
from ..repositories.paper_repo import PaperRepository
from ..repositories.idea_repo import IdeaRepository
from ..services.rag_service import RAGService, PaperNotFoundError as RAGPaperNotFoundError
from ..services.idea_service import IdeaService, DuplicateIdeaError, InvalidChunkIdsError
from ..services.ai_provider import ProviderConfigurationError, ProviderRequestError, ProviderResponseError, EmbeddingDimensionError
from ..services.multi_paper_rag_service import MultiPaperRAGService
from ..agents.reader_agent import reader_node
from ..agents.state import AgentState

logger = logging.getLogger(__name__)

_session_factory = _default_session_factory


def set_session_factory(factory):
    global _session_factory
    _session_factory = factory


def get_session_factory():
    return _session_factory


def _dt_to_iso(val: Any) -> str | None:
    if val is None:
        return None
    return val.isoformat() if hasattr(val, "isoformat") else str(val)


async def tool_search_papers(query: str, limit: int = 5, user_id: str = "default") -> dict[str, Any]:
    limit = max(1, min(limit, 20))
    query = query.strip()[:200]

    async with _session_factory() as session:
        repo = PaperRepository(session)
        papers = await repo.list_papers(user_id=user_id)
        results = []
        for p in papers:
            if query.lower() in p.title.lower() or query.lower() in p.filename.lower():
                chunk_count = await repo.get_chunk_count(p.id)
                results.append({
                    "paper_id": p.id,
                    "title": p.title,
                    "filename": p.filename,
                    "status": p.status,
                    "chunk_count": chunk_count,
                    "created_at": _dt_to_iso(p.created_at),
                })
                if len(results) >= limit:
                    break
        return {"papers": results}


async def tool_get_paper_summary(paper_id: int, user_id: str = "default") -> dict[str, Any]:
    async with _session_factory() as session:
        repo = PaperRepository(session)
        paper = await repo.get_paper(paper_id, user_id=user_id)
        if paper is None:
            return {"error": f"Paper {paper_id} not found", "paper_id": paper_id}

        if paper.status != "completed":
            return {"error": f"Paper {paper_id} is not ready (status={paper.status})", "paper_id": paper_id}

        state = AgentState(paper_id=paper_id, task_type="summarize_paper", user_id=user_id)
        try:
            state = await reader_node(session, state)
        except Exception:
            logger.exception("ReaderAgent failed for paper %s", paper_id)
            return {"error": "internal_error: failed to generate summary", "paper_id": paper_id}

        if state.status == "failed":
            return {"error": "internal_error: summary generation failed", "paper_id": paper_id}

        return {
            "paper_id": paper_id,
            "summary": state.summary,
            "confidence": state.confidence,
        }


async def tool_search_ideas(query: str, limit: int = 5, user_id: str = "default") -> dict[str, Any]:
    limit = max(1, min(limit, 20))
    query = query.strip()[:200]

    async with _session_factory() as session:
        repo = IdeaRepository(session)
        ideas = await repo.list_ideas(user_id=user_id)
        results = []
        for idea in ideas:
            tags_str = idea.tags if isinstance(idea.tags, str) else "[]"
            searchable = f"{idea.title} {idea.summary} {tags_str}".lower()
            if query.lower() in searchable:
                source_count = await repo.get_source_count(idea.id)
                try:
                    tags_list = json.loads(tags_str) if isinstance(tags_str, str) else []
                except (json.JSONDecodeError, TypeError):
                    tags_list = []
                if not isinstance(tags_list, list):
                    tags_list = []
                results.append({
                    "idea_id": idea.id,
                    "title": idea.title,
                    "summary": idea.summary,
                    "paper_id": idea.paper_id,
                    "tags": tags_list,
                    "confidence": idea.confidence,
                    "source_count": source_count,
                    "created_at": _dt_to_iso(idea.created_at),
                })
                if len(results) >= limit:
                    break
        return {"ideas": results}


async def tool_recommend_citations(
    draft_text: str,
    paper_id: int | None = None,
    paper_ids: list[int] | None = None,
    limit: int = 5,
    user_id: str = "default",
) -> dict[str, Any]:
    limit = max(1, min(limit, 10))
    draft_text = draft_text.strip()[:2000]

    if not draft_text:
        return {"error": "validation_error: draft_text is required"}

    if paper_id is not None:
        async with _session_factory() as session:
            paper_repo = PaperRepository(session)
            paper = await paper_repo.get_paper(paper_id, user_id=user_id)
            if paper is None:
                return {"error": f"validation_error: paper {paper_id} not found", "paper_id": paper_id}

            rag = RAGService(session, user_id=user_id)
            try:
                result = await rag.ask(paper_id, draft_text)
            except RAGPaperNotFoundError:
                return {"error": f"validation_error: paper {paper_id} not found", "paper_id": paper_id}
            except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError, EmbeddingDimensionError):
                logger.exception("Provider failed for recommend_citations paper %s", paper_id)
                return {"error": "internal_error: citation recommendation failed", "paper_id": paper_id}
            except Exception:
                logger.exception("Citation recommendation failed for paper %s", paper_id)
                return {"error": "internal_error: citation recommendation failed", "paper_id": paper_id}

            sources = [
                {
                    "paper_id": paper_id,
                    "paper_title": paper.title,
                    "chunk_id": s.chunk_id,
                    "page_start": s.page_start,
                    "page_end": s.page_end,
                    "text_excerpt": s.text_excerpt,
                    "score": s.score,
                }
                for s in result.sources[:limit]
            ]

            return {
                "paper_id": paper_id,
                "answer": result.answer,
                "rag_status": result.status,
                "confidence": result.confidence,
                "sources": sources,
            }

    if paper_ids is not None:
        async with _session_factory() as session:
            paper_repo = PaperRepository(session)
            for pid in paper_ids:
                p = await paper_repo.get_paper(pid, user_id=user_id)
                if p is None:
                    return {"error": f"validation_error: paper {pid} not found"}

            rag = MultiPaperRAGService(session, user_id=user_id)
            try:
                result = await rag.ask(
                    question=draft_text,
                    paper_ids=paper_ids,
                    top_k=limit,
                )
            except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError, EmbeddingDimensionError):
                logger.exception("Provider failed for recommend_citations paper_ids %s", paper_ids)
                return {"error": "internal_error: citation recommendation failed", "paper_ids": paper_ids}
            except Exception:
                logger.exception("Citation recommendation failed for paper_ids %s", paper_ids)
                return {"error": "internal_error: citation recommendation failed", "paper_ids": paper_ids}

            sources = [
                {
                    "paper_id": s.paper_id,
                    "paper_title": s.paper_title,
                    "chunk_id": s.chunk_id,
                    "page_start": s.page_start,
                    "page_end": s.page_end,
                    "text_excerpt": s.text_excerpt,
                    "score": s.score,
                }
                for s in result.sources[:limit]
            ]

            return {
                "answer": result.answer,
                "rag_status": result.status,
                "confidence": result.confidence,
                "sources": sources,
            }

    async with _session_factory() as session:
        rag = MultiPaperRAGService(session, user_id=user_id)
        try:
            result = await rag.ask(question=draft_text, top_k=limit)
        except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError, EmbeddingDimensionError):
            logger.exception("Provider failed for recommend_citations (all papers)")
            return {"error": "internal_error: citation recommendation failed"}
        except Exception:
            logger.exception("Citation recommendation failed (all papers)")
            return {"error": "internal_error: citation recommendation failed"}

        sources = [
            {
                "paper_id": s.paper_id,
                "paper_title": s.paper_title,
                "chunk_id": s.chunk_id,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "text_excerpt": s.text_excerpt,
                "score": s.score,
            }
            for s in result.sources[:limit]
        ]

        return {
            "answer": result.answer,
            "rag_status": result.status,
            "confidence": result.confidence,
            "sources": sources,
        }


async def tool_search_paper_chunks(
    query: str,
    paper_ids: list[int] | None = None,
    limit: int = 10,
    user_id: str = "default",
) -> dict[str, Any]:
    limit = max(1, min(limit, 20))
    query = query.strip()[:200]

    if not query:
        return {"error": "validation_error: query is required"}

    if paper_ids is not None:
        async with _session_factory() as session:
            paper_repo = PaperRepository(session)
            for pid in paper_ids:
                p = await paper_repo.get_paper(pid, user_id=user_id)
                if p is None:
                    return {"error": f"validation_error: paper {pid} not found"}

    async with _session_factory() as session:
        rag = MultiPaperRAGService(session, user_id=user_id)
        try:
            results = await rag.search(query=query, paper_ids=paper_ids, top_k=limit)
        except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError, EmbeddingDimensionError):
            logger.exception("Provider failed for search_paper_chunks")
            return {"error": "internal_error: search failed"}
        except Exception:
            logger.exception("Search failed for search_paper_chunks")
            return {"error": "internal_error: search failed"}

        return {
            "results": [
                {
                    "paper_id": r.paper_id,
                    "paper_title": r.paper_title,
                    "chunk_id": r.chunk_id,
                    "chunk_index": r.chunk_index,
                    "page_start": r.page_start,
                    "page_end": r.page_end,
                    "text_excerpt": r.text_excerpt,
                    "score": r.score,
                }
                for r in results
            ]
        }


async def tool_save_research_idea(
    title: str,
    summary: str,
    tags: list[str],
    source_paper_ids: list[int],
    user_id: str = "default",
) -> dict[str, Any]:
    title = title.strip()
    summary = summary.strip()

    if not title or len(title) > 120:
        return {"error": "validation_error: title must be non-empty and <= 120 chars"}
    if not summary or len(summary) > 1000:
        return {"error": "validation_error: summary must be non-empty and <= 1000 chars"}
    if len(tags) > 10:
        return {"error": "validation_error: tags must have at most 10 items"}
    if not source_paper_ids or len(source_paper_ids) != 1:
        return {"error": "validation_error: source_paper_ids must contain exactly 1 paper_id"}

    paper_id = source_paper_ids[0]

    async with _session_factory() as session:
        paper_repo = PaperRepository(session)
        idea_service = IdeaService(session)

        paper = await paper_repo.get_paper(paper_id, user_id=user_id)
        if paper is None:
            return {"error": f"validation_error: paper {paper_id} not found"}
        chunks = await paper_repo.get_chunks_by_paper(paper_id)
        if not chunks:
            return {"error": f"validation_error: paper {paper_id} has no chunks, cannot create source-backed idea"}

        source_chunk_ids = [chunks[0].id]

        try:
            idea = await idea_service.save_idea(
                paper_id=paper_id,
                title=title,
                summary=summary,
                research_question="Saved via MCP",
                method_hint="Saved via MCP",
                tags=tags[:10],
                source_chunk_ids=source_chunk_ids,
                confidence=0.5,
                user_id=user_id,
            )
            await session.commit()
        except DuplicateIdeaError:
            await session.rollback()
            return {"error": f"conflict_error: duplicate idea title under paper {paper_id}"}
        except InvalidChunkIdsError:
            await session.rollback()
            return {"error": "validation_error: invalid source chunk ids"}
        except Exception:
            logger.exception("Failed to save research idea")
            await session.rollback()
            return {"error": "internal_error: failed to save research idea"}

        idea_repo = IdeaRepository(session)
        idea_sources = await idea_repo.get_idea_sources(idea.id)

        return {
            "idea_id": idea.id,
            "title": idea.title,
            "paper_id": paper_id,
            "sources": [
                {
                    "chunk_id": s.chunk_id,
                    "paper_id": s.paper_id,
                    "page_start": s.page_start,
                    "page_end": s.page_end,
                    "text_excerpt": s.text_excerpt,
                }
                for s in idea_sources
            ],
        }
