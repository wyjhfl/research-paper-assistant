from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun


class AgentRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, run: AgentRun) -> AgentRun:
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def get_run_by_run_id(self, run_id: str, user_id: str | None = None) -> AgentRun | None:
        stmt = select(AgentRun).where(AgentRun.run_id == run_id)
        if user_id is not None:
            stmt = stmt.where(AgentRun.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_run_status(
        self,
        run_id: str,
        status: str,
        output_json: str | None = None,
        error_message: str | None = None,
    ) -> AgentRun | None:
        run = await self.get_run_by_run_id(run_id)
        if run is None:
            return None
        run.status = status
        if output_json is not None:
            run.output_json = output_json
        if error_message is not None:
            run.error_message = error_message
        await self.session.flush()
        await self.session.refresh(run)
        return run
