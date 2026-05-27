import json
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import JobRun
from ..repositories.job_repo import JobRepository

VALID_JOB_TYPES = ("process_paper", "rebuild_embeddings", "agent_run", "real_model_eval")


class JobService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = JobRepository(db)

    async def create_job(
        self,
        user_id: str,
        job_type: str,
        input_data: dict | None = None,
        max_attempts: int | None = None,
    ) -> JobRun:
        if job_type not in VALID_JOB_TYPES:
            raise ValueError(f"Invalid job_type: {job_type}")
        if max_attempts is None:
            max_attempts = settings.JOB_MAX_ATTEMPTS
        job_id = f"job_{secrets.token_urlsafe(24)}"
        job = JobRun(
            job_id=job_id,
            user_id=user_id,
            job_type=job_type,
            status="pending",
            input_json=json.dumps(input_data or {}, ensure_ascii=False),
            max_attempts=max_attempts,
        )
        return await self.repo.create(job)

    async def get_job(self, user_id: str, job_id: str) -> JobRun | None:
        job = await self.repo.get_by_job_id(job_id)
        if job is None or job.user_id != user_id:
            return None
        return job

    async def list_jobs(
        self,
        user_id: str,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
    ) -> list[JobRun]:
        return await self.repo.list_by_user(user_id, status=status, job_type=job_type, limit=limit)

    async def cancel_job(self, user_id: str, job_id: str) -> bool:
        return await self.repo.cancel_job(job_id, user_id)

    async def get_worker_health(self, user_id: str) -> dict:
        counts = await self.repo.count_by_user_and_status(user_id)
        stale_count = await self.repo.count_stale_running(user_id, settings.JOB_STALE_RUNNING_SECONDS)
        return {
            "worker_enabled": settings.JOB_WORKER_ENABLED,
            "poll_interval_seconds": settings.JOB_POLL_INTERVAL_SECONDS,
            "max_attempts_default": settings.JOB_MAX_ATTEMPTS,
            "stale_running_seconds": settings.JOB_STALE_RUNNING_SECONDS,
            "running_count": counts.get("running", 0),
            "pending_count": counts.get("pending", 0),
            "failed_count": counts.get("failed", 0),
            "stale_running_count": stale_count,
        }

    async def retry_job(self, user_id: str, job_id: str) -> bool | str:
        return await self.repo.retry_job(job_id, user_id)
