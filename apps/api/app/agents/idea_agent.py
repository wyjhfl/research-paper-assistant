from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .state import AgentState
from ..services.idea_service import IdeaService

logger = logging.getLogger(__name__)


async def idea_node(session: AsyncSession, state: AgentState) -> AgentState:
    service = IdeaService(session)
    try:
        candidates = await service.extract_ideas(state.paper_id, user_id=state.user_id)
    except Exception as e:
        state.status = "failed"
        state.warnings.append(f"Idea extraction failed: {str(e)}")
        return state

    state.ideas = [
        {
            "title": c.title,
            "summary": c.summary,
            "research_question": c.research_question,
            "method_hint": c.method_hint,
            "tags": c.tags,
            "source_chunk_ids": c.source_chunk_ids,
            "confidence": c.confidence,
        }
        for c in candidates
    ]

    if state.ideas:
        avg_conf = sum(i["confidence"] for i in state.ideas) / len(state.ideas)
        state.confidence = round(avg_conf, 2)
    else:
        state.confidence = 0.0

    logger.info(
        "IdeaAgent produced %d ideas for paper_id=%d, run_id=%s",
        len(state.ideas),
        state.paper_id,
        state.run_id,
    )
    return state
