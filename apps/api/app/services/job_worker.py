import json
import logging
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..config import settings
from ..models import JobRun
from ..repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)

_AGENT_RUN_ALLOWED_KEYS = {
    "run_id", "status", "task_type", "confidence", "warning_count",
}
_AGENT_RUN_OUTPUT_ALLOWED_COUNT_KEYS = {
    "source_count", "idea_count", "chunk_count", "candidate_count",
}
_MESSAGE_MAX_LEN = 300


def safe_job_output(job_type: str, result: dict | None) -> dict | None:
    if result is None:
        return None
    if job_type == "process_paper":
        return {
            "paper_id": result.get("paper_id"),
            "status": result.get("status"),
        }
    elif job_type == "rebuild_embeddings":
        return {
            "paper_id": result.get("paper_id"),
            "chunks_embedded": result.get("chunks_embedded"),
        }
    elif job_type == "real_model_eval":
        msg = result.get("message", "")
        if isinstance(msg, str) and len(msg) > _MESSAGE_MAX_LEN:
            msg = msg[:_MESSAGE_MAX_LEN] + "..."
        return {
            "status": result.get("status"),
            "message": msg,
        }
    elif job_type == "agent_run":
        safe: dict = {}
        for k in _AGENT_RUN_ALLOWED_KEYS:
            if k in result:
                safe[k] = result[k]
        if "warnings" in result and isinstance(result["warnings"], list):
            safe["warning_count"] = len(result["warnings"])
        output = result.get("output")
        if isinstance(output, dict):
            safe["output_keys"] = list(output.keys())
            if "sources" in output and isinstance(output["sources"], list):
                safe["source_count"] = len(output["sources"])
            if "ideas" in output and isinstance(output["ideas"], list):
                safe["idea_count"] = len(output["ideas"])
            if "retrieved_chunks" in output and isinstance(output["retrieved_chunks"], list):
                safe["chunk_count"] = len(output["retrieved_chunks"])
            if "candidates" in output and isinstance(output["candidates"], list):
                safe["candidate_count"] = len(output["candidates"])
            if "rag_status" in output:
                safe["rag_status"] = output["rag_status"]
        for k in _AGENT_RUN_OUTPUT_ALLOWED_COUNT_KEYS:
            if k in result and k not in safe:
                safe[k] = result[k]
        if "confidence" not in safe and "confidence" in result:
            safe["confidence"] = result["confidence"]
        return safe
    logger.warning("safe_job_output: unknown job_type '%s', returning minimal safe summary", job_type)
    return {"status": result.get("status")}


class JobWorker:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        if not settings.JOB_WORKER_ENABLED:
            logger.info("Job worker disabled")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Job worker started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Job worker stopped")

    async def _loop(self):
        from ..database import engine
        factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        while self._running:
            try:
                async with factory() as session:
                    claimed = await self._run_one(session)
                    if not claimed:
                        await asyncio.sleep(settings.JOB_POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Job worker loop error")
                await asyncio.sleep(settings.JOB_POLL_INTERVAL_SECONDS)

    async def _run_one(self, session: AsyncSession) -> bool:
        repo = JobRepository(session)
        job = await repo.claim_pending()
        if job is None:
            return False
        job_id = job.job_id
        attempts_after_claim = job.attempts
        max_attempts = job.max_attempts
        logger.info("Processing job %s type=%s attempt=%d/%d", job_id, job.job_type, attempts_after_claim, max_attempts)
        try:
            result = await self._execute(job, session)
            safe_result = safe_job_output(job.job_type, result)
            output = json.dumps(safe_result, ensure_ascii=False) if safe_result is not None else None
            await repo.mark_completed(job_id, output)
            await session.commit()
            logger.info("Job %s completed", job_id)
        except Exception as exc:
            await session.rollback()
            async with session.begin():
                repo2 = JobRepository(session)
                safe_msg = f"{type(exc).__name__}: job execution failed"
                await repo2.mark_failed_with_attempts(job_id, safe_msg, attempts_after_claim, max_attempts)
            logger.exception("Job %s failed (attempt %d/%d)", job_id, attempts_after_claim, max_attempts)
        return True

    async def _execute(self, job: JobRun, session: AsyncSession) -> dict | None:
        input_data = json.loads(job.input_json)
        if job.job_type == "process_paper":
            from ..services.paper_service import PaperService
            svc = PaperService(session, user_id=job.user_id)
            paper = await svc.process_paper(input_data["paper_id"])
            return {"paper_id": paper.id, "status": paper.status}
        elif job.job_type == "rebuild_embeddings":
            from ..services.paper_service import PaperService
            svc = PaperService(session, user_id=job.user_id)
            count = await svc.rebuild_embeddings(input_data["paper_id"])
            return {"paper_id": input_data["paper_id"], "chunks_embedded": count}
        elif job.job_type == "agent_run":
            from ..services.agent_run_service import AgentRunService
            svc = AgentRunService(session)
            result = await svc.run_agent(
                task_type=input_data.get("task_type", ""),
                paper_id=input_data.get("paper_id"),
                paper_ids=input_data.get("paper_ids"),
                question=input_data.get("question", ""),
                draft_text=input_data.get("draft_text", ""),
                user_id=job.user_id,
            )
            return result
        elif job.job_type == "real_model_eval":
            return {"status": "unsupported", "message": "real_model_eval not yet implemented as async job"}
        else:
            raise ValueError(f"Unknown job_type: {job.job_type}")

    async def run_one_sync(self) -> bool:
        from ..database import engine
        factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            return await self._run_one(session)


job_worker = JobWorker()
