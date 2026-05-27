from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..config import settings


class JobCreateRequest(BaseModel):
    job_type: Literal["process_paper", "rebuild_embeddings", "agent_run", "real_model_eval"]
    input: dict = {}
    max_attempts: int = Field(default=settings.JOB_MAX_ATTEMPTS, ge=1, le=10)


class JobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    input_summary: str | None = None
    output_summary: str | None = None
    error_message: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    attempts: int = 0
    max_attempts: int = 1
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int


class JobCancelResponse(BaseModel):
    ok: bool


class WorkerHealthResponse(BaseModel):
    worker_enabled: bool
    poll_interval_seconds: float
    max_attempts_default: int
    stale_running_seconds: int
    running_count: int
    pending_count: int
    failed_count: int
    stale_running_count: int


class JobRetryResponse(BaseModel):
    ok: bool
