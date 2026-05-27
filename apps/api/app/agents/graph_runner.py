from __future__ import annotations

import logging
from typing import Callable, Awaitable

from .state import AgentState

logger = logging.getLogger(__name__)

NodeFunc = Callable[[AgentState], Awaitable[AgentState]]


class GraphRunner:
    def __init__(self):
        self._nodes: list[tuple[str, NodeFunc]] = []

    def add_node(self, name: str, func: NodeFunc) -> "GraphRunner":
        self._nodes.append((name, func))
        return self

    async def run(self, initial_state: AgentState) -> AgentState:
        state = initial_state
        for name, func in self._nodes:
            if state.status == "failed":
                logger.info(
                    "Agent node '%s' skipped for failed run_id=%s",
                    name,
                    state.run_id,
                )
                continue
            logger.info("Agent node '%s' starting for run_id=%s", name, state.run_id)
            state = await func(state)
            logger.info(
                "Agent node '%s' completed for run_id=%s, status=%s",
                name,
                state.run_id,
                state.status,
            )
        return state
