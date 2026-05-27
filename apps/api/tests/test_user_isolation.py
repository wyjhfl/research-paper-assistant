from __future__ import annotations

import pytest
import inspect
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models import Paper, Idea, PaperChunk, AgentRun
from app.mcp import tools as mcp_tools
from app.mcp.server import (
    search_papers, get_paper_summary, search_ideas,
    recommend_citations, search_paper_chunks, save_research_idea,
)
from app.agents.state import AgentState
from app.agents.reader_agent import reader_node
from app.services.idea_service import IdeaService


def _get_session_factory():
    from app.mcp.tools import get_session_factory
    return get_session_factory()


async def _create_paper_for_user(user_id: str, title: str = "Test Paper") -> int:
    factory = _get_session_factory()
    async with factory() as session:
        paper = Paper(
            title=title,
            filename=f"{title}.pdf",
            file_path=f"uploads/{user_id}/{title}.pdf",
            status="completed",
            user_id=user_id,
        )
        session.add(paper)
        await session.flush()
        await session.refresh(paper)

        chunk = PaperChunk(
            paper_id=paper.id,
            chunk_index=0,
            text="This is a test chunk about machine learning and neural networks.",
            page_start=1,
            page_end=2,
        )
        session.add(chunk)
        await session.flush()
        await session.commit()
        return paper.id


async def _create_idea_for_user(user_id: str, paper_id: int, title: str = "Test Idea") -> int:
    factory = _get_session_factory()
    async with factory() as session:
        idea = Idea(
            paper_id=paper_id,
            title=title,
            summary="Test summary",
            research_question="Test question",
            method_hint="Test method",
            tags="[]",
            confidence=0.5,
            status="saved",
            user_id=user_id,
        )
        session.add(idea)
        await session.flush()
        await session.refresh(idea)
        await session.commit()
        return idea.id


async def _create_agent_run_for_user(user_id: str, paper_id: int) -> str:
    factory = _get_session_factory()
    run_id = "test-run-isolation-001"
    async with factory() as session:
        run = AgentRun(
            run_id=run_id,
            user_id=user_id,
            task_type="summarize_paper",
            status="completed",
            paper_id=paper_id,
            input_json="{}",
        )
        session.add(run)
        await session.commit()
    return run_id


@pytest.mark.asyncio
async def test_missing_x_user_id_uses_default():
    paper_id = await _create_paper_for_user("default", "Default Paper")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/papers")
    assert resp.status_code == 200
    data = resp.json()
    assert any(p["id"] == paper_id for p in data["papers"])


@pytest.mark.asyncio
async def test_user_a_upload_user_b_cannot_see():
    paper_id = await _create_paper_for_user("user-a", "User A Paper")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/papers", headers={"X-User-Id": "user-b"})
    assert resp.status_code == 200
    data = resp.json()
    assert not any(p["id"] == paper_id for p in data["papers"])


@pytest.mark.asyncio
async def test_user_b_cannot_access_user_a_paper():
    paper_id = await _create_paper_for_user("user-a", "Secret Paper")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/papers/{paper_id}", headers={"X-User-Id": "user-b"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_user_b_cannot_ask_user_a_paper():
    paper_id = await _create_paper_for_user("user-a", "Ask Paper")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/papers/{paper_id}/ask",
            json={"question": "What is this about?"},
            headers={"X-User-Id": "user-b"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_multi_paper_ask_does_not_cross_user():
    paper_id_a = await _create_paper_for_user("user-a", "Paper A")
    paper_id_b = await _create_paper_for_user("user-b", "Paper B")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/papers/ask",
            json={"question": "test", "paper_ids": [paper_id_a, paper_id_b]},
            headers={"X-User-Id": "user-a"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_paper_search_does_not_cross_user():
    paper_id_b = await _create_paper_for_user("user-b", "Search Paper")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/papers/search",
            json={"query": "machine learning", "paper_ids": [paper_id_b]},
            headers={"X-User-Id": "user-a"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_idea_list_does_not_cross_user():
    paper_id = await _create_paper_for_user("user-a", "Idea Paper")
    idea_id = await _create_idea_for_user("user-a", paper_id, "User A Idea")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ideas", headers={"X-User-Id": "user-b"})
    assert resp.status_code == 200
    data = resp.json()
    assert not any(i["id"] == idea_id for i in data["ideas"])


@pytest.mark.asyncio
async def test_user_b_cannot_delete_user_a_idea():
    paper_id = await _create_paper_for_user("user-a", "Delete Idea Paper")
    idea_id = await _create_idea_for_user("user-a", paper_id, "Protected Idea")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(f"/ideas/{idea_id}", headers={"X-User-Id": "user-b"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_run_isolation():
    paper_id = await _create_paper_for_user("user-a", "Agent Paper")
    run_id = await _create_agent_run_for_user("user-a", paper_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/agent/runs/{run_id}", headers={"X-User-Id": "user-b"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_x_user_id_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/papers", headers={"X-User-Id": "invalid user id!"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_mcp_default_user_id_no_break():
    result = await mcp_tools.tool_search_papers(query="test", user_id="default")
    assert "papers" in result


@pytest.mark.asyncio
async def test_mcp_user_id_isolation():
    await _create_paper_for_user("user-a", "MCP Paper A")
    await _create_paper_for_user("user-b", "MCP Paper B")

    result_a = await mcp_tools.tool_search_papers(query="MCP", user_id="user-a")
    result_b = await mcp_tools.tool_search_papers(query="MCP", user_id="user-b")

    titles_a = [p["title"] for p in result_a["papers"]]
    titles_b = [p["title"] for p in result_b["papers"]]

    assert "MCP Paper A" in titles_a
    assert "MCP Paper B" not in titles_a
    assert "MCP Paper B" in titles_b
    assert "MCP Paper A" not in titles_b


@pytest.mark.asyncio
async def test_mcp_server_wrapper_has_user_id_param():
    for func in [search_papers, get_paper_summary, search_ideas,
                 recommend_citations, search_paper_chunks, save_research_idea]:
        sig = inspect.signature(func)
        assert "user_id" in sig.parameters, f"{func.__name__} missing user_id param"
        assert sig.parameters["user_id"].default == "default", f"{func.__name__} user_id default is not 'default'"


@pytest.mark.asyncio
async def test_reader_agent_respects_user_id():
    paper_id = await _create_paper_for_user("reader_a", "Reader Agent Test Paper")

    factory = _get_session_factory()
    async with factory() as session:
        state = AgentState(
            paper_id=paper_id,
            task_type="summarize_paper",
            user_id="reader_b",
        )
        result = await reader_node(session, state)
        assert result.status == "failed"


@pytest.mark.asyncio
async def test_idea_service_rag_uses_user_id():
    paper_id = await _create_paper_for_user("idea_rag_user", "Idea RAG Test Paper")

    factory = _get_session_factory()
    async with factory() as session:
        with patch("app.services.idea_service.RAGService") as MockRAG:
            mock_rag_instance = AsyncMock()
            mock_rag_instance.ask = AsyncMock(return_value=type("R", (), {"sources": [], "status": "insufficient_context", "answer": "", "confidence": 0.0})())
            MockRAG.return_value = mock_rag_instance

            with patch("app.services.idea_service.get_llm_provider") as mock_llm:
                mock_llm_instance = AsyncMock()
                mock_llm_instance.generate_answer = AsyncMock(return_value='{"ideas": []}')
                mock_llm.return_value = mock_llm_instance

                service = IdeaService(session)
                try:
                    await service.extract_ideas(paper_id, user_id="idea_rag_user")
                except Exception:
                    pass

                MockRAG.assert_called_once_with(session, user_id="idea_rag_user")
