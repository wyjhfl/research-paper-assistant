import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_user_id
from ..services.job_service import JobService, VALID_JOB_TYPES
from ..schemas.job import (
    JobCreateRequest, JobResponse, JobListResponse,
    JobCancelResponse, WorkerHealthResponse, JobRetryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

_AGENT_RUN_SENSITIVE_KEYS = {"question", "draft_text", "answer", "output_text"}
_TRUNCATE_MAX_LEN = 120


def _safe_input_summary(job_type: str, input_json: str | None) -> str | None:
    if input_json is None:
        return None
    try:
        data = json.loads(input_json)
    except (json.JSONDecodeError, TypeError):
        return "<invalid input>"
    if job_type == "process_paper":
        return f"paper_id={data.get('paper_id')}"
    elif job_type == "rebuild_embeddings":
        return f"paper_id={data.get('paper_id')}"
    elif job_type == "agent_run":
        parts = [f"task_type={data.get('task_type', '')}"]
        paper_id = data.get("paper_id")
        if paper_id is not None:
            parts.append(f"paper_id={paper_id}")
        paper_ids = data.get("paper_ids")
        if paper_ids:
            parts.append(f"paper_ids={paper_ids}")
        return ", ".join(parts)
    elif job_type == "real_model_eval":
        return "eval run"
    return json.dumps({k: v for k, v in data.items() if k not in _AGENT_RUN_SENSITIVE_KEYS}, ensure_ascii=False)


def _safe_output_summary(job_type: str, output_json: str | None) -> str | None:
    if output_json is None:
        return None
    try:
        data = json.loads(output_json)
    except (json.JSONDecodeError, TypeError):
        return "<invalid output>"
    if job_type == "process_paper":
        return f"paper_id={data.get('paper_id')}, status={data.get('status')}"
    elif job_type == "rebuild_embeddings":
        return f"paper_id={data.get('paper_id')}, chunks_embedded={data.get('chunks_embedded')}"
    elif job_type == "agent_run":
        run_id = data.get("run_id", "")
        status = data.get("status", "")
        return f"run_id={run_id}, status={status}"
    elif job_type == "real_model_eval":
        return "eval completed"
    safe = {k: v for k, v in data.items() if k not in _AGENT_RUN_SENSITIVE_KEYS}
    text = json.dumps(safe, ensure_ascii=False)
    if len(text) > _TRUNCATE_MAX_LEN:
        text = text[:_TRUNCATE_MAX_LEN] + "..."
    return text


@router.get("/worker/health", response_model=WorkerHealthResponse)
async def worker_health(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = JobService(db)
    return await service.get_worker_health(user_id)


@router.post("", status_code=201, response_model=JobResponse)
async def create_job(
    req: JobCreateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = JobService(db)
    try:
        job = await service.create_job(
            user_id=user_id,
            job_type=req.job_type,
            input_data=req.input,
            max_attempts=req.max_attempts,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return _job_to_response(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: str | None = Query(None),
    job_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = JobService(db)
    jobs = await service.list_jobs(user_id, status=status, job_type=job_type, limit=limit)
    return {
        "jobs": [_job_to_response(j) for j in jobs],
        "total": len(jobs),
    }


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = JobService(db)
    job = await service.get_job(user_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = JobService(db)
    ok = await service.cancel_job(user_id, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found or cannot be cancelled")
    await db.commit()
    return {"ok": True}


@router.post("/{job_id}/retry", response_model=JobRetryResponse)
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = JobService(db)
    result = await service.retry_job(user_id, job_id)
    if result is False:
        raise HTTPException(status_code=404, detail="Job not found")
    if result == "not_failed":
        raise HTTPException(status_code=409, detail="Only failed jobs can be retried")
    await db.commit()
    return {"ok": True}


def _job_to_response(job) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        input_summary=_safe_input_summary(job.job_type, job.input_json),
        output_summary=_safe_output_summary(job.job_type, job.output_json),
        error_message=job.error_message,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
