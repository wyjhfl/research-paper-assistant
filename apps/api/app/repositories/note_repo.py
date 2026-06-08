from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ResearchNote


class ResearchNoteRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_note(self, note: ResearchNote) -> ResearchNote:
        self.session.add(note)
        await self.session.flush()
        await self.session.refresh(note)
        return note

    async def get_note(self, note_id: int, user_id: str | None = None) -> ResearchNote | None:
        stmt = select(ResearchNote).where(ResearchNote.id == note_id)
        if user_id is not None:
            stmt = stmt.where(ResearchNote.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_notes(self, user_id: str | None = None, limit: int = 100) -> list[ResearchNote]:
        stmt = select(ResearchNote).order_by(ResearchNote.created_at.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(ResearchNote.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_note(self, note_id: int, user_id: str | None = None) -> bool:
        note = await self.get_note(note_id, user_id=user_id)
        if note is None:
            return False
        await self.session.delete(note)
        await self.session.flush()
        return True
