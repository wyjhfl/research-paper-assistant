from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..repositories.agent_run_repo import AgentRunRepository
from ..agents.state import AgentState
from ..agents.langgraph_runner import LangGraphRunner
from ..agents.supervisor import VALID_TASK_TYPES
from ..models import AgentRun
from ..repositories.paper_repo import PaperRepository
from .model_call_audit_service import record_model_call

logger = logging.getLogger(__name__)

_VALID_RUN_STATUSES = {"pending", "running", "completed", "failed"}


class AgentRunService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentRunRepository(session)
        self.paper_repo = PaperRepository(session)

    async def run_agent(
        self,
        task_type: str,
        paper_id: int | None = None,
        question: str = "",
        draft_text: str = "",
        user_id: str = "default",
        paper_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex[:16]

        input_data = {
            "task_type": task_type,
            "paper_id": paper_id,
            "question": question,
            "draft_text": draft_text,
            "paper_ids": paper_ids or [],
        }

        agent_run = AgentRun(
            run_id=run_id,
            user_id=user_id,
            task_type=task_type,
            status="pending",
            paper_id=paper_id,
            input_json=json.dumps(input_data, ensure_ascii=False),
        )
        await self.repo.create_run(agent_run)
        await self.session.commit()

        try:
            await self.repo.update_run_status(run_id, "running")
            await self.session.commit()

            agent_start = time.monotonic()

            state = AgentState(
                run_id=run_id,
                user_id=user_id,
                task_type=task_type,
                paper_id=paper_id,
                paper_ids=paper_ids or [],
                question=question,
                draft_text=draft_text,
            )

            runner = LangGraphRunner(self.session)
            state = await runner.run(state)

            final_status = state.status
            if final_status not in _VALID_RUN_STATUSES:
                final_status = "completed"

            output = self._state_to_output(state)
            output_json = json.dumps(output, ensure_ascii=False, default=str)

            error_message = None
            if final_status == "failed" and state.warnings:
                error_message = "; ".join(state.warnings)

            await self.repo.update_run_status(
                run_id, final_status, output_json=output_json, error_message=error_message,
            )
            await self.session.commit()

            await record_model_call(
                user_id=user_id,
                operation="agent_run",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="success",
                duration_ms=int((time.monotonic() - agent_start) * 1000),
                input_count=1,
                input_chars=0,
                output_chars=0,
                metadata={"agent_task_type": task_type, "paper_id": paper_id},
            )

            return {
                "run_id": run_id,
                "status": final_status,
                "task_type": task_type,
                "output": output,
                "warnings": state.warnings,
                "confidence": state.confidence,
            }

        except Exception as e:
            logger.exception("Agent run failed for run_id=%s", run_id)
            try:
                await self.repo.update_run_status(
                    run_id, "failed", error_message=str(e),
                )
                await self.session.commit()
            except Exception:
                logger.exception("Failed to update agent_run status for run_id=%s", run_id)

            await record_model_call(
                user_id=user_id,
                operation="agent_run",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="failed",
                duration_ms=int((time.monotonic() - agent_start) * 1000),
                input_count=1,
                input_chars=0,
                output_chars=0,
                error_type=type(e).__name__,
                error_message=str(e),
                metadata={"agent_task_type": task_type, "paper_id": paper_id},
            )

            return {
                "run_id": run_id,
                "status": "failed",
                "task_type": task_type,
                "output": {},
                "warnings": [str(e)],
                "confidence": 0.0,
            }

    async def get_run(self, run_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        run = await self.repo.get_run_by_run_id(run_id, user_id=user_id)
        if run is None:
            return None

        output = None
        if run.output_json:
            try:
                output = json.loads(run.output_json)
            except json.JSONDecodeError:
                output = None

        return {
            "run_id": run.run_id,
            "task_type": run.task_type,
            "status": run.status,
            "paper_id": run.paper_id,
            "input": json.loads(run.input_json) if run.input_json else {},
            "output": output,
            "error_message": run.error_message,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }

    def _state_to_output(self, state: AgentState) -> dict[str, Any]:
        if state.task_type == "summarize_paper":
            return {
                "summary": state.summary,
                "retrieved_chunks": state.retrieved_chunks,
            }
        elif state.task_type == "extract_ideas":
            return {
                "ideas": state.ideas,
            }
        elif state.task_type == "recommend_citations":
            return {
                "answer": state.answer,
                "sources": state.sources,
                "rag_status": state.rag_status,
            }
        elif state.task_type == "recommend_citations_multi":
            return {
                "answer": state.answer,
                "sources": state.sources,
                "rag_status": state.rag_status,
            }
        return {}
