from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    task_type: str
    paper_id: int | None = None
    question: str = ""
    draft_text: str = ""
    paper_ids: list[int] | None = Field(default=None, max_length=50)


class AgentRunResponse(BaseModel):
    run_id: str
    status: str
    task_type: str
    output: dict[str, Any]
    warnings: list[str]
    confidence: float


class AgentRunDetailResponse(BaseModel):
    run_id: str
    task_type: str
    status: str
    paper_id: int | None
    input: dict[str, Any]
    output: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
