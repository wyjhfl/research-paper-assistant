from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .state import AgentState
from ..services.multi_paper_rag_service import MultiPaperRAGService

logger = logging.getLogger(__name__)


async def multi_citation_node(session: AsyncSession, state: AgentState) -> AgentState:
    query = state.question or state.draft_text

    rag = MultiPaperRAGService(session, user_id=state.user_id)
    try:
        paper_ids = state.paper_ids if state.paper_ids else None
        result = await rag.ask(query, paper_ids=paper_ids)
    except Exception as e:
        state.status = "failed"
        state.warnings.append(f"Multi-citation retrieval failed: {type(e).__name__}")
        return state

    state.answer = result.answer
    state.rag_status = result.status
    state.confidence = result.confidence
    state.sources = [
        {
            "paper_id": s.paper_id,
            "paper_title": s.paper_title,
            "chunk_id": s.chunk_id,
            "chunk_index": s.chunk_index,
            "page_start": s.page_start,
            "page_end": s.page_end,
            "text_excerpt": s.text_excerpt,
            "score": s.score,
        }
        for s in result.sources
    ]

    logger.info(
        "MultiCitationAgent produced answer for run_id=%s, rag_status=%s",
        state.run_id,
        state.rag_status,
    )
    return state
