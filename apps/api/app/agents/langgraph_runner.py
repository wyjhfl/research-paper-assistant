from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import StateGraph, START, END

from .state import AgentState
from .supervisor import supervisor_node
from .reader_agent import reader_node
from .idea_agent import idea_node
from .citation_agent import citation_node
from .multi_citation_agent import multi_citation_node
from .reflection_agent import reflection_node

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _state_to_dict(state: AgentState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "user_id": state.user_id,
        "task_type": state.task_type,
        "paper_id": state.paper_id,
        "paper_ids": state.paper_ids,
        "question": state.question,
        "draft_text": state.draft_text,
        "retrieved_chunks": state.retrieved_chunks,
        "ideas": state.ideas,
        "answer": state.answer,
        "summary": state.summary,
        "sources": state.sources,
        "warnings": state.warnings,
        "confidence": state.confidence,
        "status": state.status,
        "rag_status": state.rag_status,
    }


def _dict_to_state(data: dict[str, Any]) -> AgentState:
    return AgentState(
        run_id=data.get("run_id", ""),
        user_id=data.get("user_id", "default"),
        task_type=data.get("task_type", ""),
        paper_id=data.get("paper_id"),
        paper_ids=data.get("paper_ids", []),
        question=data.get("question", ""),
        draft_text=data.get("draft_text", ""),
        retrieved_chunks=data.get("retrieved_chunks", []),
        ideas=data.get("ideas", []),
        answer=data.get("answer", ""),
        summary=data.get("summary", {}),
        sources=data.get("sources", []),
        warnings=data.get("warnings", []),
        confidence=data.get("confidence", 0.0),
        status=data.get("status", "pending"),
        rag_status=data.get("rag_status", ""),
    )


def _route_after_supervisor(data: dict[str, Any]) -> str:
    if data.get("status") == "failed":
        return "reflection"
    task_type = data.get("task_type", "")
    routing = {
        "summarize_paper": "reader",
        "extract_ideas": "idea",
        "recommend_citations": "citation",
        "recommend_citations_multi": "multi_citation",
    }
    return routing.get(task_type, "reflection")


def _route_after_business(data: dict[str, Any]) -> str:
    if data.get("status") == "failed":
        return END
    return "reflection"


def _route_after_reflection(data: dict[str, Any]) -> str:
    return END


def build_graph(session: AsyncSession) -> StateGraph:
    async def _supervisor(data: dict[str, Any]) -> dict[str, Any]:
        state = _dict_to_state(data)
        state = await supervisor_node(state)
        return _state_to_dict(state)

    async def _reader(data: dict[str, Any]) -> dict[str, Any]:
        state = _dict_to_state(data)
        state = await reader_node(session, state)
        return _state_to_dict(state)

    async def _idea(data: dict[str, Any]) -> dict[str, Any]:
        state = _dict_to_state(data)
        state = await idea_node(session, state)
        return _state_to_dict(state)

    async def _citation(data: dict[str, Any]) -> dict[str, Any]:
        state = _dict_to_state(data)
        state = await citation_node(session, state)
        return _state_to_dict(state)

    async def _multi_citation(data: dict[str, Any]) -> dict[str, Any]:
        state = _dict_to_state(data)
        state = await multi_citation_node(session, state)
        return _state_to_dict(state)

    async def _reflection(data: dict[str, Any]) -> dict[str, Any]:
        state = _dict_to_state(data)
        state = await reflection_node(state)
        return _state_to_dict(state)

    graph = StateGraph(dict)

    graph.add_node("supervisor", _supervisor)
    graph.add_node("reader", _reader)
    graph.add_node("idea", _idea)
    graph.add_node("citation", _citation)
    graph.add_node("multi_citation", _multi_citation)
    graph.add_node("reflection", _reflection)

    graph.add_edge(START, "supervisor")

    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            "reader": "reader",
            "idea": "idea",
            "citation": "citation",
            "multi_citation": "multi_citation",
            "reflection": "reflection",
        },
    )

    graph.add_conditional_edges(
        "reader",
        _route_after_business,
        {"reflection": "reflection", END: END},
    )
    graph.add_conditional_edges(
        "idea",
        _route_after_business,
        {"reflection": "reflection", END: END},
    )
    graph.add_conditional_edges(
        "citation",
        _route_after_business,
        {"reflection": "reflection", END: END},
    )
    graph.add_conditional_edges(
        "multi_citation",
        _route_after_business,
        {"reflection": "reflection", END: END},
    )

    graph.add_conditional_edges(
        "reflection",
        _route_after_reflection,
        {END: END},
    )

    return graph


class LangGraphRunner:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._graph = build_graph(session)
        self._compiled = self._graph.compile()

    async def run(self, initial_state: AgentState) -> AgentState:
        input_dict = _state_to_dict(initial_state)
        result_dict = await self._compiled.ainvoke(input_dict)
        return _dict_to_state(result_dict)
