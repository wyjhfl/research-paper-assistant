from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .state import AgentState
from ..repositories.paper_repo import PaperRepository

logger = logging.getLogger(__name__)


async def reader_node(session: AsyncSession, state: AgentState) -> AgentState:
    repo = PaperRepository(session)
    paper = await repo.get_paper(state.paper_id, user_id=state.user_id)
    if paper is None:
        state.status = "failed"
        state.warnings.append(f"Paper {state.paper_id} not found")
        return state

    if paper.status != "completed":
        state.status = "failed"
        state.warnings.append(f"Paper {state.paper_id} is not ready (status={paper.status})")
        return state

    chunks = await repo.get_chunks_by_paper(state.paper_id)
    if not chunks:
        state.summary = {
            "title": paper.title,
            "overview": "该论文暂无文本片段，无法生成摘要。",
            "key_points": [],
            "limitations": [],
            "source_chunk_ids": [],
            "confidence": 0.0,
        }
        state.confidence = 0.0
        return state

    all_text = " ".join(c.text for c in chunks)
    sentences = [s.strip() for s in all_text.split(".") if len(s.strip()) > 20]
    key_points = sentences[:5] if sentences else [all_text[:200]]

    source_chunk_ids = [c.id for c in chunks[:5]]

    overview = all_text[:500] if len(all_text) > 500 else all_text

    limitations = []
    limitation_keywords = ["limitation", "future work", "drawback", "weakness", "不足", "局限"]
    for chunk in chunks:
        text_lower = chunk.text.lower()
        for kw in limitation_keywords:
            if kw in text_lower:
                excerpt = chunk.text[:200]
                if excerpt not in limitations:
                    limitations.append(excerpt)
                break
        if len(limitations) >= 3:
            break

    if not limitations:
        limitations = ["未在论文中明确指出局限性。"]

    confidence = min(len(chunks) / 10.0, 1.0) * 0.7 + 0.2

    state.summary = {
        "title": paper.title,
        "overview": overview,
        "key_points": key_points,
        "limitations": limitations,
        "source_chunk_ids": source_chunk_ids,
        "confidence": round(confidence, 2),
    }
    state.confidence = round(confidence, 2)
    state.retrieved_chunks = [
        {
            "chunk_id": c.id,
            "chunk_index": c.chunk_index,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "text_excerpt": c.text[:300] + ("..." if len(c.text) > 300 else ""),
        }
        for c in chunks[:5]
    ]

    logger.info(
        "ReaderAgent produced summary for paper_id=%d, run_id=%s",
        state.paper_id,
        state.run_id,
    )
    return state
