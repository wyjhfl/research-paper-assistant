from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import JobRun


class JobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_job_id(self, job_id: str) -> JobRun | None:
        result = await self.db.execute(
            select(JobRun).where(JobRun.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: str,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
    ) -> list[JobRun]:
        stmt = select(JobRun).where(JobRun.user_id == user_id).order_by(JobRun.created_at.desc())
        if status:
            stmt = stmt.where(JobRun.status == status)
        if job_type:
            stmt = stmt.where(JobRun.job_type == job_type)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, job: JobRun) -> JobRun:
        self.db.add(job)
        await self.db.flush()
        return job

    async def claim_pending(self) -> JobRun | None:
        result = await self.db.execute(
            select(JobRun)
            .where(JobRun.status == "pending")
            .order_by(JobRun.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.locked_at = datetime.now(timezone.utc)
        job.started_at = datetime.now(timezone.utc)
        await self.db.flush()
        return job

    async def mark_completed(self, job_id: str, output_json: str | None = None) -> None:
        await self.db.execute(
            update(JobRun)
            .where(JobRun.job_id == job_id)
            .values(
                status="completed",
                output_json=output_json,
                finished_at=datetime.now(timezone.utc),
            )
        )
        await self.db.flush()

    async def mark_failed_with_attempts(
        self,
        job_id: str,
        error_message: str,
        attempts: int,
        max_attempts: int,
    ) -> None:
        if attempts >= max_attempts:
            new_status = "failed"
            finished_at = datetime.now(timezone.utc)
        else:
            new_status = "pending"
            finished_at = None
        await self.db.execute(
            update(JobRun)
            .where(JobRun.job_id == job_id)
            .values(
                status=new_status,
                error_message=error_message,
                attempts=attempts,
                finished_at=finished_at,
                locked_at=None,
            )
        )
        await self.db.flush()

    async def update_progress(self, job_id: str, current: int, total: int) -> None:
        await self.db.execute(
            update(JobRun)
            .where(JobRun.job_id == job_id)
            .values(progress_current=current, progress_total=total)
        )
        await self.db.flush()

    async def cancel_job(self, job_id: str, user_id: str) -> bool:
        job = await self.get_by_job_id(job_id)
        if job is None or job.user_id != user_id:
            return False
        if job.status not in ("pending",):
            return False
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True

    async def count_by_user_and_status(self, user_id: str) -> dict[str, int]:
        stmt = (
            select(JobRun.status, func.count(JobRun.job_id))
            .where(JobRun.user_id == user_id)
            .group_by(JobRun.status)
        )
        result = await self.db.execute(stmt)
        counts: dict[str, int] = {}
        for status, count in result.all():
            counts[status] = count
        return counts

    async def count_stale_running(self, user_id: str, stale_seconds: int) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - stale_seconds
        stmt = select(func.count(JobRun.job_id)).where(
            JobRun.user_id == user_id,
            JobRun.status == "running",
        )
        result = await self.db.execute(stmt)
        all_running = list(
            (await self.db.execute(
                select(JobRun).where(
                    JobRun.user_id == user_id,
                    JobRun.status == "running",
                )
            )).scalars().all()
        )
        stale_count = 0
        for job in all_running:
            if job.locked_at and job.locked_at.timestamp() < cutoff:
                stale_count += 1
        return stale_count

    async def retry_job(self, job_id: str, user_id: str) -> bool | str:
        job = await self.get_by_job_id(job_id)
        if job is None or job.user_id != user_id:
            return False
        if job.status != "failed":
            return "not_failed"
        job.status = "pending"
        job.attempts = 0
        job.error_message = None
        job.locked_at = None
        job.started_at = None
        job.finished_at = None
        await self.db.flush()
        return True
