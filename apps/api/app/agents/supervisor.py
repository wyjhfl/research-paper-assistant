from __future__ import annotations

import logging

from .state import AgentState

logger = logging.getLogger(__name__)

VALID_TASK_TYPES = {"summarize_paper", "extract_ideas", "recommend_citations", "recommend_citations_multi"}


async def supervisor_node(state: AgentState) -> AgentState:
    if state.task_type not in VALID_TASK_TYPES:
        state.status = "failed"
        state.warnings.append(f"Invalid task_type: {state.task_type}")
        return state
    state.status = "running"
    logger.info(
        "Supervisor dispatched task_type=%s for run_id=%s",
        state.task_type,
        state.run_id,
    )
    return state
