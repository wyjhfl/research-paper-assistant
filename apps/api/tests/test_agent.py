import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.main import app
from app.config import settings

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
        files={"file": ("agent_test.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_agent_summarize_paper_returns_summary(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization. "
        "The framework uses attention mechanisms to improve performance on benchmark tasks."
    )
    resp = await client.post("/agent/run", json={
        "task_type": "summarize_paper",
        "paper_id": paper_id,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"]
    assert data["status"] == "completed"
    assert data["task_type"] == "summarize_paper"
    assert "summary" in data["output"]
    summary = data["output"]["summary"]
    assert summary["title"]
    assert summary["overview"]
    assert isinstance(summary["key_points"], list)
    assert isinstance(summary["source_chunk_ids"], list)


@pytest.mark.asyncio
async def test_agent_extract_ideas_returns_ideas_with_source_chunk_ids(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization. "
        "The framework uses attention mechanisms to improve performance on benchmark tasks."
    )
    resp = await client.post("/agent/run", json={
        "task_type": "extract_ideas",
        "paper_id": paper_id,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "ideas" in data["output"]
    ideas = data["output"]["ideas"]
    assert len(ideas) >= 1
    for idea in ideas:
        assert idea["title"]
        assert isinstance(idea["source_chunk_ids"], list)
        assert len(idea["source_chunk_ids"]) >= 1


@pytest.mark.asyncio
async def test_agent_recommend_citations_returns_sources(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "Deep learning models achieve state of the art results in computer vision."
    )
    resp = await client.post("/agent/run", json={
        "task_type": "recommend_citations",
        "paper_id": paper_id,
        "question": "What do deep learning models achieve?",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "sources" in data["output"]
    assert "rag_status" in data["output"]
    assert data["output"]["rag_status"] in ("answered", "insufficient_context")


@pytest.mark.asyncio
async def test_agent_invalid_task_type_returns_400(client: AsyncClient):
    resp = await client.post("/agent/run", json={
        "task_type": "invalid_task",
        "paper_id": 1,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_agent_paper_not_found_returns_404(client: AsyncClient):
    resp = await client.post("/agent/run", json={
        "task_type": "summarize_paper",
        "paper_id": 99999,
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_recommend_citations_missing_question_and_draft_returns_400(client: AsyncClient):
    paper_id = await _upload_paper(client, "Some content for testing.")
    resp = await client.post("/agent/run", json={
        "task_type": "recommend_citations",
        "paper_id": paper_id,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_agent_run_completed_creates_db_record(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning."
    )
    resp = await client.post("/agent/run", json={
        "task_type": "summarize_paper",
        "paper_id": paper_id,
    })
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    async with _test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT status, output_json FROM agent_runs WHERE run_id = :rid"),
            {"rid": run_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "completed"
        assert row[1] is not None


@pytest.mark.asyncio
async def test_agent_run_failed_creates_db_record(client: AsyncClient):
    from unittest.mock import patch, AsyncMock

    paper_id = await _upload_paper(client, "Some content for testing.")

    with patch("app.agents.langgraph_runner.reader_node", new_callable=AsyncMock) as mock_reader:
        async def _fail_reader(session, state):
            state.status = "failed"
            state.warnings.append("Simulated reader failure")
            return state
        mock_reader.side_effect = _fail_reader

        resp = await client.post("/agent/run", json={
            "task_type": "summarize_paper",
            "paper_id": paper_id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"

        async with _test_engine.begin() as conn:
            result = await conn.execute(
                text("SELECT status, error_message FROM agent_runs WHERE run_id = :rid"),
                {"rid": data["run_id"]},
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "failed"
            assert row[1] is not None


@pytest.mark.asyncio
async def test_get_agent_run_returns_detail(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning."
    )
    run_resp = await client.post("/agent/run", json={
        "task_type": "summarize_paper",
        "paper_id": paper_id,
    })
    run_id = run_resp.json()["run_id"]

    detail_resp = await client.get(f"/agent/runs/{run_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["run_id"] == run_id
    assert detail["task_type"] == "summarize_paper"
    assert detail["status"] == "completed"
    assert detail["output"] is not None
    assert detail["created_at"]


@pytest.mark.asyncio
async def test_get_agent_run_not_found_returns_404(client: AsyncClient):
    resp = await client.get("/agent/runs/nonexistent_run_id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_summarize_paper_missing_paper_id_returns_400(client: AsyncClient):
    resp = await client.post("/agent/run", json={
        "task_type": "summarize_paper",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_extract_ideas_missing_paper_id_returns_400(client: AsyncClient):
    resp = await client.post("/agent/run", json={
        "task_type": "extract_ideas",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_recommend_citations_missing_paper_id_returns_400(client: AsyncClient):
    resp = await client.post("/agent/run", json={
        "task_type": "recommend_citations",
        "question": "What is this about?",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_recommend_citations_insufficient_context_completed_with_rag_status(client: AsyncClient):
    paper_id = await _upload_paper(client, "Some content for testing.")
    resp = await client.post("/agent/run", json={
        "task_type": "recommend_citations",
        "paper_id": paper_id,
        "question": "What is the recipe for chocolate cake?",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["output"]["rag_status"] == "insufficient_context"
    assert len(data["warnings"]) > 0

    async with _test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT status FROM agent_runs WHERE run_id = :rid"),
            {"rid": data["run_id"]},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "completed"


@pytest.mark.asyncio
async def test_agent_runs_status_never_insufficient_context(client: AsyncClient):
    paper_id = await _upload_paper(client, "Some content for testing.")
    resp = await client.post("/agent/run", json={
        "task_type": "recommend_citations",
        "paper_id": paper_id,
        "question": "What is the recipe for chocolate cake?",
    })
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    async with _test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT DISTINCT status FROM agent_runs"),
        )
        statuses = [row[0] for row in result.fetchall()]
        for s in statuses:
            assert s in ("pending", "running", "completed", "failed")


@pytest.mark.asyncio
async def test_recommend_citations_multi_insufficient_context_completed_with_rag_status(client: AsyncClient):
    paper_id = await _upload_paper(client, "Some content for testing.")
    resp = await client.post("/agent/run", json={
        "task_type": "recommend_citations_multi",
        "paper_ids": [paper_id],
        "question": "What is the recipe for chocolate cake?",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["output"]["rag_status"] == "insufficient_context"
    assert len(data["warnings"]) > 0

    async with _test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT status FROM agent_runs WHERE run_id = :rid"),
            {"rid": data["run_id"]},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "completed"


@pytest.mark.asyncio
async def test_graph_runner_short_circuits_on_failed(client: AsyncClient):
    from unittest.mock import patch, AsyncMock

    paper_id = await _upload_paper(client, "Some content for testing.")

    with patch("app.agents.langgraph_runner.reader_node", new_callable=AsyncMock) as mock_reader, \
         patch("app.agents.langgraph_runner.reflection_node", new_callable=AsyncMock) as mock_reflection:

        async def _fail_reader(session, state):
            state.status = "failed"
            state.warnings.append("Simulated failure")
            return state

        mock_reader.side_effect = _fail_reader

        async def _noop_reflection(state):
            return state

        mock_reflection.side_effect = _noop_reflection

        resp = await client.post("/agent/run", json={
            "task_type": "summarize_paper",
            "paper_id": paper_id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        mock_reflection.assert_not_called()
