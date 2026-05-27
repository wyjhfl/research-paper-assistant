from __future__ import annotations

import logging

from .state import AgentState

logger = logging.getLogger(__name__)


async def reflection_node(state: AgentState) -> AgentState:
    if state.status == "failed":
        logger.info(
            "ReflectionAgent skipped for failed run_id=%s",
            state.run_id,
        )
        return state

    task_type = state.task_type
    warnings: list[str] = []

    if task_type == "summarize_paper":
        summary = state.summary
        if not summary:
            warnings.append("No summary produced.")
        else:
            key_points = summary.get("key_points", [])
            source_chunk_ids = summary.get("source_chunk_ids", [])
            if not key_points:
                warnings.append("Summary has no key_points.")
            if not source_chunk_ids:
                warnings.append("Summary has no source_chunk_ids; key_points lack source support.")

    elif task_type == "extract_ideas":
        ideas = state.ideas
        if not ideas:
            warnings.append("No ideas produced.")
        else:
            for i, idea in enumerate(ideas):
                if not idea.get("source_chunk_ids"):
                    warnings.append(
                        f"Idea #{i + 1} '{idea.get('title', 'untitled')}' has no source_chunk_ids."
                    )
                    idea["confidence"] = round(idea.get("confidence", 0.5) * 0.5, 2)
            if state.confidence > 0:
                has_no_source = any(not idea.get("source_chunk_ids") for idea in ideas)
                if has_no_source:
                    state.confidence = round(state.confidence * 0.7, 2)

    elif task_type in ("recommend_citations", "recommend_citations_multi"):
        if not state.sources:
            warnings.append("No sources found for citation recommendation.")
        if state.rag_status == "insufficient_context":
            warnings.append("Insufficient context for citation recommendation.")

    state.warnings.extend(warnings)
    state.status = "completed"

    logger.info(
        "ReflectionAgent added %d warnings for run_id=%s, final status=%s",
        len(warnings),
        state.run_id,
        state.status,
    )
    return state
