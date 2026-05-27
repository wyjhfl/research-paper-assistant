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


async def _upload_paper(client: AsyncClient, text: str, filename: str = "test.pdf") -> int:
    pdf = _make_pdf(text)
    resp = await client.post(
        "/papers/upload",
        files={"file": (filename, pdf, "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_multi_paper_ask_without_paper_ids_searches_all(client: AsyncClient):
    pid1 = await _upload_paper(client, "Neural networks learn from data patterns.", "nn.pdf")
    pid2 = await _upload_paper(client, "Reinforcement learning optimizes decision making.", "rl.pdf")

    resp = await client.post(
        "/papers/ask",
        json={"question": "What do neural networks learn?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("answered", "insufficient_context")
    if data["sources"]:
        found_ids = {s["paper_id"] for s in data["sources"]}
        assert found_ids.issubset({pid1, pid2})


@pytest.mark.asyncio
async def test_multi_paper_ask_with_paper_ids_limits_scope(client: AsyncClient):
    pid1 = await _upload_paper(client, "Paper Alpha discusses quantum computing advances.", "alpha.pdf")
    pid2 = await _upload_paper(client, "Paper Beta covers ocean biology research.", "beta.pdf")

    resp = await client.post(
        "/papers/ask",
        json={"question": "What is discussed?", "paper_ids": [pid1]},
    )
    assert resp.status_code == 200
    data = resp.json()
    for source in data["sources"]:
        assert source["paper_id"] == pid1


@pytest.mark.asyncio
async def test_paper_search_returns_results(client: AsyncClient):
    await _upload_paper(client, "Convolutional neural networks for image classification.", "cnn.pdf")

    resp = await client.post(
        "/papers/search",
        json={"query": "neural networks"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    if data["results"]:
        assert "paper_id" in data["results"][0]
        assert "paper_title" in data["results"][0]
        assert "chunk_id" in data["results"][0]
        assert "score" in data["results"][0]


@pytest.mark.asyncio
async def test_multi_paper_ask_empty_question_returns_422(client: AsyncClient):
    resp = await client.post(
        "/papers/ask",
        json={"question": "   "},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_paper_search_empty_query_returns_422(client: AsyncClient):
    resp = await client.post(
        "/papers/search",
        json={"query": "   "},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_multi_paper_ask_nonexistent_paper_id_returns_404(client: AsyncClient):
    resp = await client.post(
        "/papers/ask",
        json={"question": "What is this?", "paper_ids": [99999]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_paper_search_nonexistent_paper_id_returns_404(client: AsyncClient):
    resp = await client.post(
        "/papers/search",
        json={"query": "test", "paper_ids": [99999]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_failed_paper_not_in_multi_search(client: AsyncClient):
    resp = await client.post(
        "/papers/upload",
        files={"file": ("bad.pdf", b"not a real pdf", "application/pdf")},
    )
    assert resp.status_code == 201
    paper_status = resp.json()["status"]
    paper_id = resp.json()["id"]

    if paper_status == "completed":
        from app.mcp.tools import get_session_factory
        from app.models import Paper
        factory = get_session_factory()
        async with factory() as session:
            paper = await session.get(Paper, paper_id)
            if paper:
                paper.status = "failed"
                await session.commit()

    search_resp = await client.post(
        "/papers/search",
        json={"query": "test query"},
    )
    assert search_resp.status_code == 200
    data = search_resp.json()
    for r in data["results"]:
        assert r["paper_id"] != paper_id


@pytest.mark.asyncio
async def test_multi_paper_sources_include_paper_title(client: AsyncClient):
    pid = await _upload_paper(client, "Deep learning models achieve state of the art results.", "dl.pdf")

    resp = await client.post(
        "/papers/ask",
        json={"question": "What do deep learning models achieve?", "paper_ids": [pid]},
    )
    assert resp.status_code == 200
    data = resp.json()
    if data["sources"]:
        for source in data["sources"]:
            assert "paper_title" in source
            assert source["paper_title"] is not None


@pytest.mark.asyncio
async def test_per_paper_limit_prevents_monopoly(client: AsyncClient):
    pid1 = await _upload_paper(client, "Alpha paper about machine learning algorithms.", "alpha.pdf")
    pid2 = await _upload_paper(client, "Beta paper about machine learning applications.", "beta.pdf")

    resp = await client.post(
        "/papers/ask",
        json={"question": "machine learning", "paper_ids": [pid1, pid2], "top_k": 8},
    )
    assert resp.status_code == 200
    data = resp.json()
    if len(data["sources"]) >= 4:
        paper_counts: dict[int, int] = {}
        for s in data["sources"]:
            paper_counts[s["paper_id"]] = paper_counts.get(s["paper_id"], 0) + 1
        for count in paper_counts.values():
            assert count <= 4


@pytest.mark.asyncio
async def test_insufficient_context_does_not_fabricate_answer(client: AsyncClient):
    pid = await _upload_paper(client, "Some unrelated content about weather.", "weather.pdf")

    resp = await client.post(
        "/papers/ask",
        json={"question": "What is the recipe for chocolate cake?", "paper_ids": [pid]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "insufficient_context"


@pytest.mark.asyncio
async def test_mcp_recommend_citations_old_paper_id_still_works(client: AsyncClient):
    from app.mcp.tools import tool_recommend_citations
    from app.mcp.context import mcp

    pid = await _upload_paper(client, "Citation test paper about AI.", "cite.pdf")

    result = await tool_recommend_citations(
        draft_text="artificial intelligence", paper_id=pid, limit=3
    )
    if "error" in result:
        assert "internal_error" not in result["error"], f"Got internal_error: {result['error']}"


@pytest.mark.asyncio
async def test_mcp_recommend_citations_paper_ids_works(client: AsyncClient):
    from app.mcp.tools import tool_recommend_citations

    pid1 = await _upload_paper(client, "Paper about neural architectures.", "arch.pdf")
    pid2 = await _upload_paper(client, "Paper about training methods.", "train.pdf")

    result = await tool_recommend_citations(
        draft_text="neural network training", paper_ids=[pid1, pid2], limit=5
    )
    if "error" in result:
        assert "internal_error" not in result["error"], f"Got internal_error: {result['error']}"


@pytest.mark.asyncio
async def test_mcp_search_paper_chunks_works(client: AsyncClient):
    from app.mcp.tools import tool_search_paper_chunks

    pid = await _upload_paper(client, "Search test paper about transformers.", "trans.pdf")

    result = await tool_search_paper_chunks(query="transformers", paper_ids=[pid], limit=5)
    assert "error" not in result
    assert "results" in result


@pytest.mark.asyncio
async def test_agent_recommend_citations_multi_completes(client: AsyncClient):
    pid = await _upload_paper(client, "Agent multi-cite paper about GANs.", "gan.pdf")

    resp = await client.post(
        "/agent/run",
        json={
            "task_type": "recommend_citations_multi",
            "question": "generative adversarial networks",
            "paper_ids": [pid],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    run_id = data["run_id"]

    status_resp = await client.get(f"/agent/runs/{run_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "completed"
    if status_data.get("output"):
        rag_status = status_data["output"].get("rag_status", "")
        assert rag_status in ("answered", "insufficient_context", "")


@pytest.mark.asyncio
async def test_agent_multi_output_rag_status_valid(client: AsyncClient):
    pid = await _upload_paper(client, "Agent status paper about NLP.", "nlp.pdf")

    resp = await client.post(
        "/agent/run",
        json={
            "task_type": "recommend_citations_multi",
            "question": "natural language processing",
            "paper_ids": [pid],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    run_id = data["run_id"]

    status_resp = await client.get(f"/agent/runs/{run_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "completed"
    if status_data.get("output"):
        rag_status = status_data["output"].get("rag_status", "")
        assert rag_status in ("answered", "insufficient_context", "")


@pytest.mark.asyncio
async def test_single_paper_ask_still_works(client: AsyncClient):
    pid = await _upload_paper(client, "Single paper ask test about robotics.", "robot.pdf")

    resp = await client.post(
        f"/papers/{pid}/ask",
        json={"question": "What is this about?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data


@pytest.mark.asyncio
async def test_agent_recommend_citations_multi_no_paper_ids_full_library(client: AsyncClient):
    await _upload_paper(client, "Full library paper about deep reinforcement learning.", "full_lib.pdf")

    resp = await client.post(
        "/agent/run",
        json={
            "task_type": "recommend_citations_multi",
            "question": "reinforcement learning",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    run_id = data["run_id"]

    status_resp = await client.get(f"/agent/runs/{run_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_recommend_citations_multi_empty_paper_ids_full_library(client: AsyncClient):
    await _upload_paper(client, "Empty list paper about graph neural networks.", "gnn.pdf")

    resp = await client.post(
        "/agent/run",
        json={
            "task_type": "recommend_citations_multi",
            "question": "graph neural networks",
            "paper_ids": [],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    run_id = data["run_id"]

    status_resp = await client.get(f"/agent/runs/{run_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_summarize_paper_without_paper_id_returns_400(client: AsyncClient):
    resp = await client.post(
        "/agent/run",
        json={
            "task_type": "summarize_paper",
        },
    )
    assert resp.status_code == 400
    assert "paper_id is required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_agent_extract_ideas_without_paper_id_returns_400(client: AsyncClient):
    resp = await client.post(
        "/agent/run",
        json={
            "task_type": "extract_ideas",
        },
    )
    assert resp.status_code == 400
    assert "paper_id is required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_agent_recommend_citations_without_paper_id_returns_400(client: AsyncClient):
    resp = await client.post(
        "/agent/run",
        json={
            "task_type": "recommend_citations",
            "question": "test question",
        },
    )
    assert resp.status_code == 400
    assert "paper_id is required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_agent_recommend_citations_multi_nonexistent_paper_ids_returns_404(client: AsyncClient):
    resp = await client.post(
        "/agent/run",
        json={
            "task_type": "recommend_citations_multi",
            "question": "test question",
            "paper_ids": [99998, 99999],
        },
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_mcp_recommend_citations_old_paper_id_no_internal_error(client: AsyncClient):
    from app.mcp.tools import tool_recommend_citations

    pid = await _upload_paper(client, "MCP old mode paper about optimization.", "opt.pdf")

    result = await tool_recommend_citations(
        draft_text="optimization methods", paper_id=pid, limit=3
    )
    if "error" in result:
        assert "internal_error" not in result["error"], f"Got internal_error: {result['error']}"


@pytest.mark.asyncio
async def test_mcp_recommend_citations_paper_ids_no_internal_error(client: AsyncClient):
    from app.mcp.tools import tool_recommend_citations

    pid1 = await _upload_paper(client, "MCP ids mode paper about clustering.", "cluster.pdf")
    pid2 = await _upload_paper(client, "MCP ids mode paper about classification.", "classify.pdf")

    result = await tool_recommend_citations(
        draft_text="clustering and classification", paper_ids=[pid1, pid2], limit=5
    )
    if "error" in result:
        assert "internal_error" not in result["error"], f"Got internal_error: {result['error']}"
