from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Paper, PaperChunk, Idea, IdeaSource
from app.services.ai_provider import get_embedding_provider
from scripts.seed_demo import DEMO_PAPERS, DEMO_IDEAS
from scripts.reset_demo import DEMO_FILENAMES

from tests.conftest import _test_session_factory


@pytest.mark.asyncio
async def test_seed_demo_importable():
    assert len(DEMO_PAPERS) == 3
    assert len(DEMO_IDEAS) == 3
    for paper_data in DEMO_PAPERS:
        assert paper_data["filename"].startswith("demo_")
        assert len(paper_data["chunks"]) >= 3


@pytest.mark.asyncio
async def test_seed_demo_creates_completed_papers():
    embedder = get_embedding_provider()

    async with _test_session_factory() as session:
        await session.execute(delete(IdeaSource))
        await session.execute(delete(Idea))
        await session.execute(delete(PaperChunk))
        await session.execute(delete(Paper).where(Paper.filename.like("demo_%")))
        await session.flush()

        for paper_data in DEMO_PAPERS:
            paper = Paper(
                title=paper_data["title"],
                filename=paper_data["filename"],
                file_path=paper_data["file_path"],
                status="completed",
            )
            session.add(paper)
            await session.flush()

            chunk_texts = [c["text"] for c in paper_data["chunks"]]
            embeddings = await embedder.embed_texts(chunk_texts)

            for i, chunk_data in enumerate(paper_data["chunks"]):
                chunk = PaperChunk(
                    paper_id=paper.id,
                    chunk_index=chunk_data["chunk_index"],
                    text=chunk_data["text"],
                    page_start=chunk_data["page_start"],
                    page_end=chunk_data["page_end"],
                    section_title=chunk_data["section_title"],
                    embedding=embeddings[i],
                )
                session.add(chunk)

        await session.commit()

        result = await session.execute(
            select(Paper).where(Paper.filename.like("demo_%"))
        )
        demo_papers = list(result.scalars().all())
        assert len(demo_papers) == 3

        for paper in demo_papers:
            assert paper.status == "completed"


@pytest.mark.asyncio
async def test_seed_demo_creates_chunks_with_embeddings():
    embedder = get_embedding_provider()

    async with _test_session_factory() as session:
        paper = Paper(
            title=DEMO_PAPERS[0]["title"],
            filename=DEMO_PAPERS[0]["filename"],
            file_path=DEMO_PAPERS[0]["file_path"],
            status="completed",
        )
        session.add(paper)
        await session.flush()

        chunk_texts = [c["text"] for c in DEMO_PAPERS[0]["chunks"]]
        embeddings = await embedder.embed_texts(chunk_texts)

        for i, chunk_data in enumerate(DEMO_PAPERS[0]["chunks"]):
            chunk = PaperChunk(
                paper_id=paper.id,
                chunk_index=chunk_data["chunk_index"],
                text=chunk_data["text"],
                page_start=chunk_data["page_start"],
                page_end=chunk_data["page_end"],
                section_title=chunk_data["section_title"],
                embedding=embeddings[i],
            )
            session.add(chunk)

        await session.commit()

        result = await session.execute(
            select(PaperChunk).where(PaperChunk.paper_id == paper.id)
        )
        chunks = list(result.scalars().all())
        assert len(chunks) >= 3

        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == settings.EMBEDDING_DIMENSION


@pytest.mark.asyncio
async def test_seed_demo_creates_ideas_with_sources():
    embedder = get_embedding_provider()

    async with _test_session_factory() as session:
        paper = Paper(
            title=DEMO_PAPERS[0]["title"],
            filename=DEMO_PAPERS[0]["filename"],
            file_path=DEMO_PAPERS[0]["file_path"],
            status="completed",
        )
        session.add(paper)
        await session.flush()

        chunk_texts = [c["text"] for c in DEMO_PAPERS[0]["chunks"]]
        embeddings = await embedder.embed_texts(chunk_texts)

        chunk_records = []
        for i, chunk_data in enumerate(DEMO_PAPERS[0]["chunks"]):
            chunk = PaperChunk(
                paper_id=paper.id,
                chunk_index=chunk_data["chunk_index"],
                text=chunk_data["text"],
                page_start=chunk_data["page_start"],
                page_end=chunk_data["page_end"],
                section_title=chunk_data["section_title"],
                embedding=embeddings[i],
            )
            session.add(chunk)
            chunk_records.append(chunk)

        await session.flush()

        idea = Idea(
            paper_id=paper.id,
            title=DEMO_IDEAS[0]["title"],
            summary=DEMO_IDEAS[0]["summary"],
            research_question=DEMO_IDEAS[0]["research_question"],
            method_hint=DEMO_IDEAS[0]["method_hint"],
            tags=DEMO_IDEAS[0]["tags"],
            confidence=DEMO_IDEAS[0]["confidence"],
            status="saved",
        )
        session.add(idea)
        await session.flush()

        for ci in DEMO_IDEAS[0]["chunk_indices"]:
            if ci < len(chunk_records):
                chunk = chunk_records[ci]
                idea_source = IdeaSource(
                    idea_id=idea.id,
                    paper_id=paper.id,
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    text_excerpt=chunk.text[:200],
                )
                session.add(idea_source)

        await session.commit()

        source_result = await session.execute(
            select(IdeaSource).where(IdeaSource.idea_id == idea.id)
        )
        sources = list(source_result.scalars().all())
        assert len(sources) >= 1


@pytest.mark.asyncio
async def test_seed_demo_idempotent_by_filename():
    async with _test_session_factory() as session:
        await session.execute(delete(IdeaSource))
        await session.execute(delete(Idea))
        await session.execute(delete(PaperChunk))
        await session.execute(delete(Paper).where(Paper.filename == DEMO_PAPERS[0]["filename"]))
        await session.flush()

        paper_data = DEMO_PAPERS[0]

        paper = Paper(
            title=paper_data["title"],
            filename=paper_data["filename"],
            file_path=paper_data["file_path"],
            status="completed",
        )
        session.add(paper)
        await session.commit()

        result = await session.execute(
            select(Paper).where(Paper.filename == paper_data["filename"])
        )
        existing = result.scalar_one_or_none()
        assert existing is not None

        result2 = await session.execute(
            select(Paper).where(Paper.filename == paper_data["filename"])
        )
        existing2 = result2.scalar_one_or_none()
        assert existing2 is not None
        assert existing2.id == existing.id

        count_result = await session.execute(
            select(Paper).where(Paper.filename == paper_data["filename"])
        )
        all_matching = list(count_result.scalars().all())
        assert len(all_matching) == 1


@pytest.mark.asyncio
async def test_reset_demo_only_deletes_demo_data():
    async with _test_session_factory() as session:
        await session.execute(delete(IdeaSource))
        await session.execute(delete(Idea))
        await session.execute(delete(PaperChunk))
        await session.execute(delete(Paper))
        await session.flush()

        assert "demo_transformer.pdf" in DEMO_FILENAMES
        assert "real_paper.pdf" not in DEMO_FILENAMES

        demo_paper = Paper(
            title=DEMO_PAPERS[0]["title"],
            filename=DEMO_PAPERS[0]["filename"],
            file_path=DEMO_PAPERS[0]["file_path"],
            status="completed",
        )
        session.add(demo_paper)

        non_demo_paper = Paper(
            title="Non-demo paper",
            filename="real_paper.pdf",
            file_path="storage/real_paper.pdf",
            status="completed",
        )
        session.add(non_demo_paper)
        await session.commit()

        for filename in DEMO_FILENAMES:
            result = await session.execute(
                select(Paper).where(Paper.filename == filename)
            )
            paper = result.scalar_one_or_none()
            if paper is None:
                continue
            await session.execute(delete(IdeaSource).where(IdeaSource.paper_id == paper.id))
            await session.execute(delete(Idea).where(Idea.paper_id == paper.id))
            await session.execute(delete(PaperChunk).where(PaperChunk.paper_id == paper.id))
            await session.execute(delete(Paper).where(Paper.id == paper.id))

        await session.commit()

        demo_result = await session.execute(
            select(Paper).where(Paper.filename.like("demo_%"))
        )
        assert len(list(demo_result.scalars().all())) == 0

        non_demo_result = await session.execute(
            select(Paper).where(Paper.filename == "real_paper.pdf")
        )
        assert non_demo_result.scalar_one_or_none() is not None
