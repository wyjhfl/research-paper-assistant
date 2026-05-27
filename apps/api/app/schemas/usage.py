from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelCallEventItem(BaseModel):
    id: int
    operation: str
    provider: str
    model: str
    status: str
    duration_ms: int
    input_count: int
    input_chars: int
    output_chars: int
    error_type: str | None
    error_message: str | None
    metadata_json: str | None
    created_at: datetime


class ModelCallListResponse(BaseModel):
    events: list[ModelCallEventItem]
    total: int


class ModelCallSummaryResponse(BaseModel):
    total_calls: int
    success_calls: int
    failed_calls: int
    avg_duration_ms: float = Field(ge=0)
    calls_by_operation: dict[str, int]
    calls_by_provider: dict[str, int]


class EvalCaseSummary(BaseModel):
    case_id: str
    type: str
    severity: str
    status: str
    duration_ms: int
    warnings: list[str] = Field(default_factory=list)


class EvalReportMetadata(BaseModel):
    llm_model: str = ""
    embedding_model: str = ""
    embedding_dimension: int = 0
    case_file: str = ""


class EvalReportTotals(BaseModel):
    total: int = 0
    passed: int = 0
    warning: int = 0
    failed: int = 0
    blocker_failed: int = 0


class EvalReportTrend(BaseModel):
    previous_report_count: int = 0
    previous_latest_timestamp: str | None = None
    passed_delta: int = 0
    warning_delta: int = 0
    failed_delta: int = 0


class EvalReportSummaryResponse(BaseModel):
    timestamp: str = ""
    can_proceed: bool = False
    metadata: EvalReportMetadata = Field(default_factory=EvalReportMetadata)
    totals: EvalReportTotals = Field(default_factory=EvalReportTotals)
    trend: EvalReportTrend = Field(default_factory=EvalReportTrend)
    cases: list[EvalCaseSummary] = Field(default_factory=list)


class StorageSummaryResponse(BaseModel):
    paper_count: int
    chunk_count: int
    storage_bytes: int
    failed_paper_count: int
