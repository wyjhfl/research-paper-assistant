from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, init_db
from app.models import Paper, PaperChunk, Idea, IdeaSource

DEMO_FILENAMES = [
    "demo_transformer.pdf",
    "demo_rag.pdf",
    "demo_multi_agent.pdf",
]


async def reset_demo():
    await init_db()

    deleted_ideas = 0
    deleted_chunks = 0
    deleted_papers = 0

    async with async_session() as session:
        for filename in DEMO_FILENAMES:
            result = await session.execute(
                select(Paper).where(Paper.filename == filename)
            )
            paper = result.scalar_one_or_none()
            if paper is None:
                print(f"  SKIP: no demo paper with filename={filename}")
                continue

            idea_result = await session.execute(
                select(Idea).where(Idea.paper_id == paper.id)
            )
            ideas = list(idea_result.scalars().all())

            for idea in ideas:
                await session.execute(
                    delete(IdeaSource).where(IdeaSource.idea_id == idea.id)
                )
                deleted_ideas += 1

            chunk_result = await session.execute(
                select(PaperChunk).where(PaperChunk.paper_id == paper.id)
            )
            chunk_count = len(list(chunk_result.scalars().all()))
            deleted_chunks += chunk_count

            await session.execute(
                delete(Idea).where(Idea.paper_id == paper.id)
            )
            await session.execute(
                delete(PaperChunk).where(PaperChunk.paper_id == paper.id)
            )
            await session.execute(
                delete(Paper).where(Paper.id == paper.id)
            )
            deleted_papers += 1

            print(f"  DELETED: {paper.title} ({chunk_count} chunks, {len(ideas)} ideas)")

        await session.commit()

    print()
    print("=" * 60)
    print("Reset Demo Summary")
    print("=" * 60)
    print(f"  Papers deleted:  {deleted_papers}")
    print(f"  Chunks deleted:  {deleted_chunks}")
    print(f"  Ideas deleted:   {deleted_ideas}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(reset_demo())
