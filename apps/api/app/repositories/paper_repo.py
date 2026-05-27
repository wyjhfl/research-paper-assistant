from __future__ import annotations

from sqlalchemy import select, func, text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Paper, PaperChunk


class PaperRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_paper(self, paper: Paper) -> Paper:
        self.session.add(paper)
        await self.session.flush()
        await self.session.refresh(paper)
        return paper

    async def get_paper(self, paper_id: int, user_id: str | None = None) -> Paper | None:
        stmt = select(Paper).where(Paper.id == paper_id)
        if user_id is not None:
            stmt = stmt.where(Paper.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_papers(self, user_id: str | None = None) -> list[Paper]:
        stmt = select(Paper).order_by(Paper.created_at.desc())
        if user_id is not None:
            stmt = stmt.where(Paper.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_paper_status(
        self, paper_id: int, status: str, error_message: str | None = None,
        user_id: str | None = None,
    ) -> Paper | None:
        paper = await self.get_paper(paper_id, user_id=user_id)
        if paper is None:
            return None
        paper.status = status
        if error_message is not None:
            paper.error_message = error_message
        await self.session.flush()
        await self.session.refresh(paper)
        return paper

    async def get_chunks_by_paper(self, paper_id: int) -> list[PaperChunk]:
        result = await self.session.execute(
            select(PaperChunk)
            .where(PaperChunk.paper_id == paper_id)
            .order_by(PaperChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def get_chunks_without_embedding(self, paper_id: int) -> list[PaperChunk]:
        result = await self.session.execute(
            select(PaperChunk)
            .where(PaperChunk.paper_id == paper_id, PaperChunk.embedding.is_(None))
            .order_by(PaperChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def get_chunk_count(self, paper_id: int) -> int:
        result = await self.session.execute(
            select(func.count(PaperChunk.id)).where(PaperChunk.paper_id == paper_id)
        )
        return result.scalar() or 0

    async def get_embedding_count(self, paper_id: int) -> int:
        result = await self.session.execute(
            select(func.count(PaperChunk.id)).where(
                PaperChunk.paper_id == paper_id,
                PaperChunk.embedding.isnot(None),
            )
        )
        return result.scalar() or 0

    async def clear_embeddings(self, paper_id: int) -> int:
        result = await self.session.execute(
            select(PaperChunk).where(PaperChunk.paper_id == paper_id)
        )
        chunks = list(result.scalars().all())
        count = 0
        for chunk in chunks:
            if chunk.embedding is not None:
                chunk.embedding = None
                count += 1
        await self.session.flush()
        return count

    async def get_completed_paper_ids(self, user_id: str | None = None) -> list[int]:
        stmt = select(Paper.id).where(Paper.status == "completed")
        if user_id is not None:
            stmt = stmt.where(Paper.user_id == user_id)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.fetchall()]
