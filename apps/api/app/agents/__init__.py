from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    run_id: str = ""
    user_id: str = "default"
    task_type: str = ""
    paper_id: int | None = None
    question: str = ""
    draft_text: str = ""
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    ideas: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "pending"
