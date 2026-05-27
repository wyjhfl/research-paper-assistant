from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .state import AgentState
from ..services.rag_service import RAGService

logger = logging.getLogger(__name__)


async def citation_node(session: AsyncSession, state: AgentState) -> AgentState:
    query = state.question or state.draft_text

    rag = RAGService(session, user_id=state.user_id)
    try:
        result = await rag.ask(state.paper_id, query)
    except Exception as e:
        state.status = "failed"
        state.warnings.append(f"Citation retrieval failed: {str(e)}")
        return state

    state.answer = result.answer
    state.rag_status = result.status
    state.confidence = result.confidence
    state.sources = [
        {
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
        "CitationAgent produced answer for paper_id=%d, run_id=%s, rag_status=%s",
        state.paper_id,
        state.run_id,
        state.rag_status,
    )
    return state
