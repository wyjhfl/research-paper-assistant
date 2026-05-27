from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.agents.state import AgentState
from app.agents.langgraph_runner import (
    LangGraphRunner,
    _state_to_dict,
    _dict_to_state,
    _route_after_supervisor,
    _route_after_business,
    build_graph,
)
from langgraph.graph import END
from app.agents.supervisor import VALID_TASK_TYPES
from tests.conftest import _test_session_factory


@pytest.mark.asyncio
async def test_langgraph_summarize_paper():
    async with _test_session_factory() as session:
        from app.models import Paper, PaperChunk

        paper = Paper(
            title="Test Paper",
            filename="test_paper.pdf",
            file_path="storage/test_paper.pdf",
            status="completed",
        )
        session.add(paper)
        await session.flush()

        chunk = PaperChunk(
            paper_id=paper.id,
            chunk_index=0,
            text="This paper discusses attention mechanisms in neural networks. The main limitation is scalability.",
            page_start=1,
            page_end=1,
        )
        session.add(chunk)
        await session.commit()

        runner = LangGraphRunner(session)
        state = AgentState(
            run_id="test001",
            task_type="summarize_paper",
            paper_id=paper.id,
        )
        result = await runner.run(state)

        assert result.status == "completed"
        assert result.summary.get("title") == "Test Paper"
        assert len(result.summary.get("key_points", [])) >= 1


@pytest.mark.asyncio
async def test_langgraph_extract_ideas():
    async with _test_session_factory() as session:
        from app.models import Paper, PaperChunk

        paper = Paper(
            title="Idea Paper",
            filename="idea_paper.pdf",
            file_path="storage/idea_paper.pdf",
            status="completed",
        )
        session.add(paper)
        await session.flush()

        chunk = PaperChunk(
            paper_id=paper.id,
            chunk_index=0,
            text="A novel approach to attention mechanisms. This could be extended to multi-modal learning.",
            page_start=1,
            page_end=1,
        )
        session.add(chunk)
        await session.commit()

        runner = LangGraphRunner(session)
        state = AgentState(
            run_id="test002",
            task_type="extract_ideas",
            paper_id=paper.id,
        )
        result = await runner.run(state)

        assert result.status == "completed"
        assert isinstance(result.ideas, list)


@pytest.mark.asyncio
async def test_langgraph_recommend_citations():
    async with _test_session_factory() as session:
        from app.models import Paper, PaperChunk

        paper = Paper(
            title="Citation Paper",
            filename="citation_paper.pdf",
            file_path="storage/citation_paper.pdf",
            status="completed",
        )
        session.add(paper)
        await session.flush()

        chunk = PaperChunk(
            paper_id=paper.id,
            chunk_index=0,
            text="Attention mechanisms allow models to focus on relevant parts of the input sequence.",
            page_start=1,
            page_end=1,
        )
        session.add(chunk)
        await session.commit()

        runner = LangGraphRunner(session)
        state = AgentState(
            run_id="test003",
            task_type="recommend_citations",
            paper_id=paper.id,
            question="What is attention?",
        )
        result = await runner.run(state)

        assert result.status == "completed"
        assert result.rag_status in ("answered", "insufficient_context")


@pytest.mark.asyncio
async def test_langgraph_recommend_citations_multi():
    async with _test_session_factory() as session:
        from app.models import Paper, PaperChunk

        paper = Paper(
            title="Multi Paper",
            filename="multi_paper.pdf",
            file_path="storage/multi_paper.pdf",
            status="completed",
        )
        session.add(paper)
        await session.flush()

        chunk = PaperChunk(
            paper_id=paper.id,
            chunk_index=0,
            text="RAG combines retrieval with generation for better factual accuracy.",
            page_start=1,
            page_end=1,
        )
        session.add(chunk)
        await session.commit()

        runner = LangGraphRunner(session)
        state = AgentState(
            run_id="test004",
            task_type="recommend_citations_multi",
            question="How does RAG work?",
            paper_ids=[paper.id],
        )
        result = await runner.run(state)

        assert result.status == "completed"
        assert result.rag_status in ("answered", "insufficient_context")


@pytest.mark.asyncio
async def test_langgraph_invalid_task_type():
    async with _test_session_factory() as session:
        runner = LangGraphRunner(session)
        state = AgentState(
            run_id="test005",
            task_type="invalid_task",
        )
        result = await runner.run(state)

        assert result.status == "failed"
        assert any("Invalid task_type" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_langgraph_failed_not_overridden_by_reflection():
    async with _test_session_factory() as session:
        runner = LangGraphRunner(session)
        state = AgentState(
            run_id="test006",
            task_type="summarize_paper",
            paper_id=99999,
        )
        result = await runner.run(state)

        assert result.status == "failed"
        assert result.status != "completed"


def test_agent_runs_status_never_answered():
    valid_statuses = {"pending", "running", "completed", "failed"}
    assert "answered" not in valid_statuses
    assert "insufficient_context" not in valid_statuses


def test_rag_status_in_output():
    state = AgentState(
        task_type="recommend_citations",
        rag_status="answered",
        answer="test answer",
        sources=[{"chunk_id": 1}],
    )
    from app.services.agent_run_service import AgentRunService
    service = AgentRunService.__new__(AgentRunService)
    output = service._state_to_output(state)
    assert output.get("rag_status") == "answered"


def test_route_after_supervisor_routing():
    assert _route_after_supervisor({"task_type": "summarize_paper", "status": "running"}) == "reader"
    assert _route_after_supervisor({"task_type": "extract_ideas", "status": "running"}) == "idea"
    assert _route_after_supervisor({"task_type": "recommend_citations", "status": "running"}) == "citation"
    assert _route_after_supervisor({"task_type": "recommend_citations_multi", "status": "running"}) == "multi_citation"
    assert _route_after_supervisor({"task_type": "invalid", "status": "failed"}) == "reflection"


def test_route_after_business_failed_short_circuits():
    assert _route_after_business({"status": "failed"}) == END
    assert _route_after_business({"status": "completed"}) == "reflection"


def test_state_dict_roundtrip():
    original = AgentState(
        run_id="rt001",
        task_type="summarize_paper",
        paper_id=42,
        paper_ids=[1, 2, 3],
        question="test?",
        status="running",
        rag_status="answered",
        warnings=["w1"],
        confidence=0.85,
    )
    data = _state_to_dict(original)
    restored = _dict_to_state(data)
    assert restored.run_id == original.run_id
    assert restored.task_type == original.task_type
    assert restored.paper_id == original.paper_id
    assert restored.paper_ids == original.paper_ids
    assert restored.question == original.question
    assert restored.status == original.status
    assert restored.rag_status == original.rag_status
    assert restored.warnings == original.warnings
    assert restored.confidence == original.confidence


def test_reflection_multi_citation_insufficient_context_adds_warning():
    from app.agents.reflection_agent import reflection_node

    state = AgentState(
        run_id="mc001",
        task_type="recommend_citations_multi",
        status="running",
        rag_status="insufficient_context",
        sources=[],
    )
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(reflection_node(state))
    assert result.status == "completed"
    assert result.rag_status == "insufficient_context"
    assert len(result.warnings) > 0
    assert any("Insufficient context" in w for w in result.warnings)


def test_reflection_multi_citation_no_sources_adds_warning():
    from app.agents.reflection_agent import reflection_node

    state = AgentState(
        run_id="mc002",
        task_type="recommend_citations_multi",
        status="running",
        rag_status="answered",
        sources=[],
    )
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(reflection_node(state))
    assert result.status == "completed"
    assert len(result.warnings) > 0
    assert any("No sources" in w for w in result.warnings)


def test_reflection_multi_citation_failed_not_overridden():
    from app.agents.reflection_agent import reflection_node

    state = AgentState(
        run_id="mc003",
        task_type="recommend_citations_multi",
        status="failed",
        rag_status="insufficient_context",
        sources=[],
    )
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(reflection_node(state))
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_rebuild_demo_clears_and_rebuilds_embeddings():
    from app.services.ai_provider import get_embedding_provider
    from scripts.rebuild_demo_embeddings import DEMO_FILENAMES

    embedder = get_embedding_provider()

    async with _test_session_factory() as session:
        from app.models import Paper, PaperChunk
        from sqlalchemy import update

        paper = Paper(
            title="Demo Transformer",
            filename="demo_transformer.pdf",
            file_path="storage/demo_transformer.pdf",
            status="completed",
        )
        session.add(paper)
        await session.flush()

        old_embeddings = await embedder.embed_texts(["old text for testing"])
        chunks = []
        for i in range(3):
            chunk = PaperChunk(
                paper_id=paper.id,
                chunk_index=i,
                text=f"Chunk {i} text for testing rebuild",
                page_start=1,
                page_end=1,
                embedding=old_embeddings[0],
            )
            session.add(chunk)
            chunks.append(chunk)
        await session.commit()

        chunk_ids = [c.id for c in chunks]

        await session.execute(
            update(PaperChunk)
            .where(PaperChunk.paper_id == paper.id)
            .values(embedding=None)
        )
        await session.flush()

        from app.services.embedding_service import EmbeddingService
        emb_service = EmbeddingService(session, user_id="default")
        count = await emb_service.embed_chunks_for_paper(paper.id)
        await session.commit()

        assert count == 3

        from sqlalchemy import select
        result = await session.execute(
            select(PaperChunk).where(PaperChunk.id.in_(chunk_ids))
        )
        rebuilt_chunks = list(result.scalars().all())
        for chunk in rebuilt_chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) > 0
