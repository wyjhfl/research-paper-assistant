from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Idea, IdeaSource


class IdeaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_idea(self, idea: Idea) -> Idea:
        self.session.add(idea)
        await self.session.flush()
        await self.session.refresh(idea)
        return idea

    async def get_idea(self, idea_id: int, user_id: str | None = None) -> Idea | None:
        stmt = select(Idea).where(Idea.id == idea_id)
        if user_id is not None:
            stmt = stmt.where(Idea.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_ideas(self, user_id: str | None = None) -> list[Idea]:
        stmt = select(Idea).order_by(Idea.created_at.desc())
        if user_id is not None:
            stmt = stmt.where(Idea.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_idea(self, idea_id: int, user_id: str | None = None) -> bool:
        idea = await self.get_idea(idea_id, user_id=user_id)
        if idea is None:
            return False
        await self.session.delete(idea)
        await self.session.flush()
        return True

    async def get_idea_by_title_and_paper(
        self, paper_id: int, title: str, user_id: str | None = None
    ) -> Idea | None:
        stmt = select(Idea).where(Idea.paper_id == paper_id, Idea.title == title)
        if user_id is not None:
            stmt = stmt.where(Idea.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_idea_source(self, source: IdeaSource) -> IdeaSource:
        self.session.add(source)
        await self.session.flush()
        await self.session.refresh(source)
        return source

    async def get_idea_sources(self, idea_id: int) -> list[IdeaSource]:
        result = await self.session.execute(
            select(IdeaSource).where(IdeaSource.idea_id == idea_id)
        )
        return list(result.scalars().all())

    async def get_source_count(self, idea_id: int) -> int:
        result = await self.session.execute(
            select(func.count(IdeaSource.id)).where(IdeaSource.idea_id == idea_id)
        )
        return result.scalar() or 0
