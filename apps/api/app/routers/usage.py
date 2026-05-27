from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..config import settings
from ..database import get_db
from ..dependencies import get_user_id
from ..models import ModelCallEvent, Paper, PaperChunk
from ..schemas.usage import (
    ModelCallListResponse,
    ModelCallSummaryResponse,
    ModelCallEventItem,
    EvalReportSummaryResponse,
    EvalCaseSummary,
    EvalReportMetadata,
    EvalReportTotals,
    EvalReportTrend,
    StorageSummaryResponse,
)
from ..services.model_call_audit_service import _SANITIZE_PATTERNS

logger = logging.getLogger(__name__)

_MAX_PREVIEW_LEN = 200

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/model-calls", response_model=ModelCallListResponse)
async def list_model_calls(
    limit: int = Query(default=50, ge=1, le=200),
    operation: str | None = Query(default=None),
    status: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    stmt = (
        select(ModelCallEvent)
        .where(ModelCallEvent.user_id == user_id)
        .order_by(ModelCallEvent.created_at.desc())
        .limit(limit)
    )
    if operation:
        stmt = stmt.where(ModelCallEvent.operation == operation)
    if status:
        stmt = stmt.where(ModelCallEvent.status == status)
    if provider:
        stmt = stmt.where(ModelCallEvent.provider == provider)

    result = await db.execute(stmt)
    events = result.scalars().all()

    return ModelCallListResponse(
        events=[
            ModelCallEventItem(
                id=e.id,
                operation=e.operation,
                provider=e.provider,
                model=e.model,
                status=e.status,
                duration_ms=e.duration_ms,
                input_count=e.input_count,
                input_chars=e.input_chars,
                output_chars=e.output_chars,
                error_type=e.error_type,
                error_message=e.error_message,
                metadata_json=e.metadata_json,
                created_at=e.created_at,
            )
            for e in events
        ],
        total=len(events),
    )


@router.get("/model-calls/summary", response_model=ModelCallSummaryResponse)
async def model_calls_summary(
    operation: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    base_where = [ModelCallEvent.user_id == user_id]
    if operation:
        base_where.append(ModelCallEvent.operation == operation)
    if provider:
        base_where.append(ModelCallEvent.provider == provider)

    total_stmt = select(func.count()).select_from(ModelCallEvent).where(*base_where)
    success_stmt = select(func.count()).select_from(ModelCallEvent).where(
        *base_where, ModelCallEvent.status == "success"
    )
    failed_stmt = select(func.count()).select_from(ModelCallEvent).where(
        *base_where, ModelCallEvent.status == "failed"
    )
    avg_duration_stmt = select(func.avg(ModelCallEvent.duration_ms)).where(*base_where)

    by_op_stmt = (
        select(ModelCallEvent.operation, func.count())
        .where(*base_where)
        .group_by(ModelCallEvent.operation)
    )
    by_prov_stmt = (
        select(ModelCallEvent.provider, func.count())
        .where(*base_where)
        .group_by(ModelCallEvent.provider)
    )

    total = (await db.execute(total_stmt)).scalar() or 0
    success_calls = (await db.execute(success_stmt)).scalar() or 0
    failed_calls = (await db.execute(failed_stmt)).scalar() or 0
    avg_duration = (await db.execute(avg_duration_stmt)).scalar() or 0.0

    by_op_rows = (await db.execute(by_op_stmt)).all()
    calls_by_operation = {row[0]: row[1] for row in by_op_rows}

    by_prov_rows = (await db.execute(by_prov_stmt)).all()
    calls_by_provider = {row[0]: row[1] for row in by_prov_rows}

    return ModelCallSummaryResponse(
        total_calls=total,
        success_calls=success_calls,
        failed_calls=failed_calls,
        avg_duration_ms=round(float(avg_duration), 1),
        calls_by_operation=calls_by_operation,
        calls_by_provider=calls_by_provider,
    )


def _get_eval_report_path() -> Path:
    env_dir = os.environ.get("EVAL_REPORT_DIR", "").strip()
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.cwd() / "artifacts" / "evals"
    return base / "real_model_eval_latest.json"


def _sanitize_eval_value(val):
    if isinstance(val, (int, float, bool)):
        return val
    s = str(val) if val is not None else ""
    for pattern, replacement in _SANITIZE_PATTERNS:
        s = pattern.sub(replacement, s)
    if len(s) > _MAX_PREVIEW_LEN:
        s = s[:_MAX_PREVIEW_LEN] + "..."
    return s


def _extract_safe_summary(data: dict) -> EvalReportSummaryResponse:
    metadata_raw = data.get("metadata", {})
    metadata = EvalReportMetadata(
        llm_model=_sanitize_eval_value(metadata_raw.get("llm_model", "")),
        embedding_model=_sanitize_eval_value(metadata_raw.get("embedding_model", "")),
        embedding_dimension=int(metadata_raw.get("embedding_dimension", 0)),
        case_file="",
    )

    totals_raw = data.get("totals", {})
    totals = EvalReportTotals(
        total=int(totals_raw.get("total", 0)),
        passed=int(totals_raw.get("passed", 0)),
        warning=int(totals_raw.get("warning", 0)),
        failed=int(totals_raw.get("failed", 0)),
        blocker_failed=int(totals_raw.get("blocker_failed", 0)),
    )

    trend_raw = data.get("trend", {})
    trend = EvalReportTrend(
        previous_report_count=int(trend_raw.get("previous_report_count", 0)),
        previous_latest_timestamp=_sanitize_eval_value(trend_raw.get("previous_latest_timestamp")),
        passed_delta=int(trend_raw.get("passed_delta", 0)),
        warning_delta=int(trend_raw.get("warning_delta", 0)),
        failed_delta=int(trend_raw.get("failed_delta", 0)),
    )

    cases: list[EvalCaseSummary] = []
    for c in data.get("cases", []):
        if not isinstance(c, dict):
            continue
        warnings_raw = c.get("warnings", [])
        safe_warnings: list[str] = []
        if isinstance(warnings_raw, list):
            for w in warnings_raw:
                safe_warnings.append(str(_sanitize_eval_value(w)))
        cases.append(EvalCaseSummary(
            case_id=_sanitize_eval_value(c.get("case_id", "")),
            type=_sanitize_eval_value(c.get("type", "")),
            severity=_sanitize_eval_value(c.get("severity", "")),
            status=_sanitize_eval_value(c.get("status", "")),
            duration_ms=int(c.get("duration_ms", 0)),
            warnings=safe_warnings,
        ))

    return EvalReportSummaryResponse(
        timestamp=_sanitize_eval_value(data.get("timestamp", "")),
        can_proceed=bool(data.get("can_proceed", False)),
        metadata=metadata,
        totals=totals,
        trend=trend,
        cases=cases,
    )


@router.get(
    "/eval-report/latest",
    response_model=EvalReportSummaryResponse,
    responses={404: {"description": "No eval report found"}},
)
async def get_latest_eval_report():
    report_path = _get_eval_report_path()
    if not report_path.exists():
        return JSONResponse(
            status_code=404,
            content={"detail": "No eval report found"},
        )
    try:
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read eval report: %s: %s", type(exc).__name__, str(exc)[:100])
        return JSONResponse(
            status_code=404,
            content={"detail": "Eval report is not readable"},
        )
    if not isinstance(data, dict):
        return JSONResponse(
            status_code=404,
            content={"detail": "Eval report format invalid"},
        )
    return _extract_safe_summary(data)


@router.get("/storage-summary", response_model=StorageSummaryResponse)
async def storage_summary(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    paper_count_stmt = select(func.count()).select_from(Paper).where(Paper.user_id == user_id)
    chunk_count_stmt = (
        select(func.count())
        .select_from(PaperChunk)
        .join(Paper, PaperChunk.paper_id == Paper.id)
        .where(Paper.user_id == user_id)
    )
    failed_count_stmt = select(func.count()).select_from(Paper).where(
        Paper.user_id == user_id, Paper.status == "failed"
    )

    paper_count = (await db.execute(paper_count_stmt)).scalar() or 0
    chunk_count = (await db.execute(chunk_count_stmt)).scalar() or 0
    failed_paper_count = (await db.execute(failed_count_stmt)).scalar() or 0

    file_paths = (await db.execute(
        select(Paper.file_path).where(Paper.user_id == user_id)
    )).scalars().all()
    storage_root = Path(settings.STORAGE_PATH).resolve()
    storage_bytes = 0
    for fp in file_paths:
        p = Path(fp).resolve()
        try:
            p.relative_to(storage_root)
        except ValueError:
            continue
        if p.exists():
            try:
                storage_bytes += p.stat().st_size
            except OSError:
                pass

    return StorageSummaryResponse(
        paper_count=paper_count,
        chunk_count=chunk_count,
        storage_bytes=storage_bytes,
        failed_paper_count=failed_paper_count,
    )
