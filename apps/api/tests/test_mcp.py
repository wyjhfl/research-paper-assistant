import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.main import app
from app.config import settings
from app.mcp.tools import (
    tool_search_papers,
    tool_get_paper_summary,
    tool_search_ideas,
    tool_recommend_citations,
    tool_save_research_idea,
)

TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "/research_assistant", "/research_assistant_test"
)

_test_engine = create_async_engine(
    TEST_DATABASE_URL, echo=False, poolclass=NullPool
)


@pytest_asyncio.fixture(scope="function")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_pdf(text: str) -> bytes:
    stream_line = f"BT /F1 12 Tf 100 750 Td ({text}) Tj ET".encode("utf-8")
    stream_len = len(stream_line)
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/"
        b"Contents 4 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>endobj\n"
    )
    pdf += f"4 0 obj<</Length {stream_len}>>stream\n".encode("utf-8")
    pdf += stream_line + b"\nendstream\nendobj\n"
    pdf += b"xref\n0 5\n"
    pdf += b"0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    obj4_offset = 266
    pdf += f"{obj4_offset:010d} 00000 n \n".encode("utf-8")
    xref_offset = obj4_offset + len(f"4 0 obj<</Length {stream_len}>>stream\n".encode("utf-8")) + stream_len + len(b"\nendstream\nendobj\n")
    pdf += b"trailer<</Size 5/Root 1 0 R>>\n"
    pdf += f"startxref\n{xref_offset}\n%%EOF\n".encode("utf-8")
    return pdf


async def _upload_paper(client: AsyncClient, text: str) -> int:
    pdf = _make_pdf(text)
    resp = await client.post(
        "/papers/upload",
        files={"file": ("mcp_test.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


_SENSITIVE_PATTERNS = ["file_path", "DATABASE_URL", "postgresql", "asyncpg", "Traceback", "traceback"]


def _assert_no_sensitive(data: dict):
    s = str(data)
    for pattern in _SENSITIVE_PATTERNS:
        assert pattern not in s, f"Sensitive pattern '{pattern}' found in tool output"


@pytest.mark.asyncio
async def test_mcp_search_papers_empty_returns_empty(client: AsyncClient):
    result = await tool_search_papers("nonexistent")
    assert result["papers"] == []


@pytest.mark.asyncio
async def test_mcp_search_papers_finds_by_title(client: AsyncClient):
    paper_id = await _upload_paper(client, "Deep learning model optimization")
    result = await tool_search_papers("mcp_test")
    assert len(result["papers"]) >= 1
    found = any(p["paper_id"] == paper_id for p in result["papers"])
    assert found


@pytest.mark.asyncio
async def test_mcp_get_paper_summary_not_found(client: AsyncClient):
    result = await tool_get_paper_summary(99999)
    assert "error" in result
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_mcp_get_paper_summary_completed_returns_summary(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization. "
        "The framework uses attention mechanisms to improve performance."
    )
    result = await tool_get_paper_summary(paper_id)
    assert "error" not in result
    assert "summary" in result
    summary = result["summary"]
    assert "source_chunk_ids" in summary
    assert isinstance(summary["source_chunk_ids"], list)


@pytest.mark.asyncio
async def test_mcp_search_ideas_empty_returns_empty(client: AsyncClient):
    result = await tool_search_ideas("nonexistent")
    assert result["ideas"] == []


@pytest.mark.asyncio
async def test_mcp_search_ideas_finds_saved_idea(client: AsyncClient):
    paper_id = await _upload_paper(client, "Method for deep learning optimization")
    save_result = await tool_save_research_idea(
        title="Novel optimization approach",
        summary="A new way to optimize models",
        tags=["optimization"],
        source_paper_ids=[paper_id],
    )
    assert "error" not in save_result
    assert "idea_id" in save_result

    result = await tool_search_ideas("optimization")
    assert len(result["ideas"]) >= 1
    idea = result["ideas"][0]
    assert "source_count" in idea
    assert "paper_id" in idea
    assert isinstance(idea["tags"], list)


@pytest.mark.asyncio
async def test_mcp_search_ideas_tags_are_list(client: AsyncClient):
    paper_id = await _upload_paper(client, "Tags list test content")
    await tool_save_research_idea(
        title="Tags test idea",
        summary="Testing tags format",
        tags=["tag1", "tag2"],
        source_paper_ids=[paper_id],
    )
    result = await tool_search_ideas("tags")
    assert len(result["ideas"]) >= 1
    for idea in result["ideas"]:
        assert isinstance(idea["tags"], list)


@pytest.mark.asyncio
async def test_mcp_recommend_citations_returns_sources_or_rag_status(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "Deep learning models achieve state of the art results in computer vision."
    )
    result = await tool_recommend_citations(
        draft_text="What do deep learning models achieve?",
        paper_id=paper_id,
    )
    assert "rag_status" in result
    assert result["rag_status"] in ("answered", "insufficient_context")
    if result["rag_status"] == "answered":
        assert len(result["sources"]) > 0


@pytest.mark.asyncio
async def test_mcp_recommend_citations_unrelated_returns_insufficient(client: AsyncClient):
    paper_id = await _upload_paper(client, "Some content for testing.")
    result = await tool_recommend_citations(
        draft_text="What is the recipe for chocolate cake?",
        paper_id=paper_id,
    )
    assert result["rag_status"] == "insufficient_context"


@pytest.mark.asyncio
async def test_mcp_recommend_citations_empty_draft_returns_error(client: AsyncClient):
    result = await tool_recommend_citations(
        draft_text="   ",
        paper_id=1,
    )
    assert "error" in result
    assert "validation_error" in result["error"]
    assert "draft_text" in result["error"]


@pytest.mark.asyncio
async def test_mcp_recommend_citations_nonexistent_paper_returns_error(client: AsyncClient):
    result = await tool_recommend_citations(
        draft_text="Some text",
        paper_id=99999,
    )
    assert "error" in result
    assert "validation_error" in result["error"]


@pytest.mark.asyncio
async def test_mcp_save_research_idea_success(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning."
    )
    result = await tool_save_research_idea(
        title="Test MCP Idea",
        summary="A test idea saved via MCP",
        tags=["test"],
        source_paper_ids=[paper_id],
    )
    assert "error" not in result
    assert "idea_id" in result
    assert result["title"] == "Test MCP Idea"
    assert result["paper_id"] == paper_id
    assert len(result["sources"]) > 0


@pytest.mark.asyncio
async def test_mcp_save_research_idea_persists_across_sessions(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "Persistence test paper content for deep learning."
    )
    result = await tool_save_research_idea(
        title="Persisted Idea",
        summary="This idea should survive session close",
        tags=["persistence"],
        source_paper_ids=[paper_id],
    )
    assert "error" not in result
    saved_idea_id = result["idea_id"]

    search_result = await tool_search_ideas("Persisted")
    assert len(search_result["ideas"]) >= 1
    found = any(i["idea_id"] == saved_idea_id for i in search_result["ideas"])
    assert found, "Saved idea not found via search_ideas in a new session"


@pytest.mark.asyncio
async def test_mcp_save_research_idea_empty_title_returns_error(client: AsyncClient):
    result = await tool_save_research_idea(
        title="",
        summary="Some summary",
        tags=["test"],
        source_paper_ids=[1],
    )
    assert "error" in result
    assert "validation_error" in result["error"]


@pytest.mark.asyncio
async def test_mcp_save_research_idea_nonexistent_paper_returns_error(client: AsyncClient):
    result = await tool_save_research_idea(
        title="Test Idea",
        summary="Some summary",
        tags=["test"],
        source_paper_ids=[99999],
    )
    assert "error" in result
    assert "validation_error" in result["error"]


@pytest.mark.asyncio
async def test_mcp_save_research_idea_multiple_paper_ids_returns_error(client: AsyncClient):
    paper_id = await _upload_paper(client, "Multi paper test content")
    result = await tool_save_research_idea(
        title="Multi Paper Idea",
        summary="Should fail with multiple paper_ids",
        tags=["test"],
        source_paper_ids=[paper_id, 99999],
    )
    assert "error" in result
    assert "validation_error" in result["error"]
    assert "exactly 1" in result["error"]


@pytest.mark.asyncio
async def test_mcp_save_research_idea_duplicate_returns_conflict_error(client: AsyncClient):
    paper_id = await _upload_paper(client, "Duplicate idea test content")
    result1 = await tool_save_research_idea(
        title="Unique Duplicate Test Idea",
        summary="First save",
        tags=["test"],
        source_paper_ids=[paper_id],
    )
    assert "error" not in result1

    result2 = await tool_save_research_idea(
        title="Unique Duplicate Test Idea",
        summary="Second save same title",
        tags=["test"],
        source_paper_ids=[paper_id],
    )
    assert "error" in result2
    assert "conflict_error" in result2["error"]


@pytest.mark.asyncio
async def test_mcp_recommend_citations_internal_error_no_leak(client: AsyncClient):
    paper_id = await _upload_paper(client, "Internal error test content")
    with patch("app.mcp.tools.RAGService") as mock_rag_cls:
        mock_rag = AsyncMock()
        mock_rag.ask.side_effect = RuntimeError("DB connection lost: postgresql+asyncpg://secret@host/db")
        mock_rag_cls.return_value = mock_rag

        result = await tool_recommend_citations(
            draft_text="test query",
            paper_id=paper_id,
        )
    assert "error" in result
    assert "internal_error" in result["error"]
    error_str = str(result)
    assert "postgresql" not in error_str
    assert "asyncpg" not in error_str
    assert "secret" not in error_str
    assert "Traceback" not in error_str


@pytest.mark.asyncio
async def test_mcp_save_research_idea_internal_error_no_leak(client: AsyncClient):
    paper_id = await _upload_paper(client, "Save internal error test content")
    with patch("app.mcp.tools.IdeaService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.save_idea.side_effect = RuntimeError("DB error: postgresql+asyncpg://secret@host/db")
        mock_svc_cls.return_value = mock_svc

        result = await tool_save_research_idea(
            title="Leak Test",
            summary="Testing internal error leak",
            tags=["test"],
            source_paper_ids=[paper_id],
        )
    assert "error" in result
    assert "internal_error" in result["error"]
    error_str = str(result)
    assert "postgresql" not in error_str
    assert "asyncpg" not in error_str
    assert "secret" not in error_str
    assert "Traceback" not in error_str


@pytest.mark.asyncio
async def test_mcp_tools_security_no_sensitive_data(client: AsyncClient):
    paper_id = await _upload_paper(client, "Security test content")

    search_result = await tool_search_papers("mcp_test")
    _assert_no_sensitive(search_result)

    summary_result = await tool_get_paper_summary(paper_id)
    _assert_no_sensitive(summary_result)

    ideas_result = await tool_search_ideas("test")
    _assert_no_sensitive(ideas_result)

    citations_result = await tool_recommend_citations(
        draft_text="test query",
        paper_id=paper_id,
    )
    _assert_no_sensitive(citations_result)

    save_result = await tool_save_research_idea(
        title="Security Test Idea",
        summary="Testing security of save output",
        tags=["security"],
        source_paper_ids=[paper_id],
    )
    assert "error" not in save_result
    _assert_no_sensitive(save_result)
