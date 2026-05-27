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
        files={"file": ("idea_test.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_extract_ideas_for_completed_paper_returns_candidates(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization. "
        "The framework uses attention mechanisms to improve performance on benchmark tasks. "
        "Our experiment results show significant improvement over baseline approaches."
    )
    resp = await client.post(f"/papers/{paper_id}/ideas/extract")
    assert resp.status_code == 200
    data = resp.json()
    assert data["paper_id"] == paper_id
    assert len(data["candidates"]) >= 1
    for c in data["candidates"]:
        assert c["title"]
        assert c["summary"]
        assert c["research_question"]
        assert c["method_hint"]
        assert len(c["tags"]) >= 1
        assert len(c["source_chunk_ids"]) >= 1
        assert 0 <= c["confidence"] <= 1


@pytest.mark.asyncio
async def test_extract_ideas_new_path_returns_candidates(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization. "
        "The framework uses attention mechanisms to improve performance on benchmark tasks."
    )
    resp = await client.post(f"/papers/{paper_id}/ideas/extract")
    assert resp.status_code == 200
    data = resp.json()
    assert data["paper_id"] == paper_id
    assert len(data["candidates"]) >= 1


@pytest.mark.asyncio
async def test_extract_ideas_for_nonexistent_paper_returns_404(client: AsyncClient):
    resp = await client.post("/papers/99999/ideas/extract")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extract_ideas_for_failed_paper_returns_400(client: AsyncClient):
    async with _test_engine.begin() as conn:
        result = await conn.execute(
            text(
                "INSERT INTO papers (title, filename, file_path, status, user_id) "
                "VALUES ('bad.pdf', 'bad.pdf', 'storage/bad.pdf', 'failed', 'default') "
                "RETURNING id"
            )
        )
        paper_id = result.fetchone()[0]

    extract_resp = await client.post(f"/papers/{paper_id}/ideas/extract")
    assert extract_resp.status_code == 400


@pytest.mark.asyncio
async def test_save_idea_creates_idea_and_sources(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization."
    )
    extract_resp = await client.post(f"/papers/{paper_id}/ideas/extract")
    candidates = extract_resp.json()["candidates"]
    assert len(candidates) >= 1

    c = candidates[0]
    save_resp = await client.post("/ideas", json={
        "paper_id": paper_id,
        "title": c["title"],
        "summary": c["summary"],
        "research_question": c["research_question"],
        "method_hint": c["method_hint"],
        "tags": c["tags"],
        "source_chunk_ids": c["source_chunk_ids"],
        "confidence": c["confidence"],
    })
    assert save_resp.status_code == 201
    data = save_resp.json()
    assert data["id"]
    assert data["title"] == c["title"]
    assert len(data["sources"]) >= 1


@pytest.mark.asyncio
async def test_duplicate_idea_title_returns_409(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization."
    )
    extract_resp = await client.post(f"/papers/{paper_id}/ideas/extract")
    candidates = extract_resp.json()["candidates"]
    c = candidates[0]

    save1 = await client.post("/ideas", json={
        "paper_id": paper_id,
        "title": c["title"],
        "summary": c["summary"],
        "research_question": c["research_question"],
        "method_hint": c["method_hint"],
        "tags": c["tags"],
        "source_chunk_ids": c["source_chunk_ids"],
        "confidence": c["confidence"],
    })
    assert save1.status_code == 201

    save2 = await client.post("/ideas", json={
        "paper_id": paper_id,
        "title": c["title"],
        "summary": "Different summary",
        "research_question": "Different question",
        "method_hint": "Different hint",
        "tags": ["different"],
        "source_chunk_ids": c["source_chunk_ids"],
        "confidence": 0.5,
    })
    assert save2.status_code == 409


@pytest.mark.asyncio
async def test_get_ideas_returns_saved_ideas(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization."
    )
    extract_resp = await client.post(f"/papers/{paper_id}/ideas/extract")
    candidates = extract_resp.json()["candidates"]
    c = candidates[0]

    await client.post("/ideas", json={
        "paper_id": paper_id,
        "title": c["title"],
        "summary": c["summary"],
        "research_question": c["research_question"],
        "method_hint": c["method_hint"],
        "tags": c["tags"],
        "source_chunk_ids": c["source_chunk_ids"],
        "confidence": c["confidence"],
    })

    list_resp = await client.get("/ideas")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] >= 1
    assert any(idea["title"] == c["title"] for idea in data["ideas"])


@pytest.mark.asyncio
async def test_get_idea_by_id_returns_sources(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization."
    )
    extract_resp = await client.post(f"/papers/{paper_id}/ideas/extract")
    candidates = extract_resp.json()["candidates"]
    c = candidates[0]

    save_resp = await client.post("/ideas", json={
        "paper_id": paper_id,
        "title": c["title"],
        "summary": c["summary"],
        "research_question": c["research_question"],
        "method_hint": c["method_hint"],
        "tags": c["tags"],
        "source_chunk_ids": c["source_chunk_ids"],
        "confidence": c["confidence"],
    })
    idea_id = save_resp.json()["id"]

    detail_resp = await client.get(f"/ideas/{idea_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["id"] == idea_id
    assert len(data["sources"]) >= 1
    for s in data["sources"]:
        assert s["paper_id"] == paper_id
        assert s["chunk_id"]
        assert s["text_excerpt"]


@pytest.mark.asyncio
async def test_delete_idea_removes_idea_and_sources(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization."
    )
    extract_resp = await client.post(f"/papers/{paper_id}/ideas/extract")
    candidates = extract_resp.json()["candidates"]
    c = candidates[0]

    save_resp = await client.post("/ideas", json={
        "paper_id": paper_id,
        "title": c["title"],
        "summary": c["summary"],
        "research_question": c["research_question"],
        "method_hint": c["method_hint"],
        "tags": c["tags"],
        "source_chunk_ids": c["source_chunk_ids"],
        "confidence": c["confidence"],
    })
    idea_id = save_resp.json()["id"]

    del_resp = await client.delete(f"/ideas/{idea_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/ideas/{idea_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_source_chunk_ids_cannot_reference_other_paper(client: AsyncClient):
    paper_a_id = await _upload_paper(
        client,
        "Paper Alpha discusses quantum computing advances."
    )
    paper_b_id = await _upload_paper(
        client,
        "Paper Beta covers ocean biology research."
    )

    async with _test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id FROM paper_chunks WHERE paper_id = :pid LIMIT 1"),
            {"pid": paper_a_id},
        )
        row = result.fetchone()
        if row is None:
            pytest.skip("No chunks found for paper A")

    save_resp = await client.post("/ideas", json={
        "paper_id": paper_b_id,
        "title": "Test Idea",
        "summary": "Test summary",
        "research_question": "Test question",
        "method_hint": "Test hint",
        "tags": ["test"],
        "source_chunk_ids": [row[0]],
        "confidence": 0.5,
    })
    assert save_resp.status_code == 400


@pytest.mark.asyncio
async def test_empty_title_or_empty_summary_returns_422(client: AsyncClient):
    paper_id = await _upload_paper(
        client,
        "This paper proposes a novel method for deep learning model optimization."
    )

    resp1 = await client.post("/ideas", json={
        "paper_id": paper_id,
        "title": "",
        "summary": "test",
        "research_question": "test",
        "method_hint": "test",
        "tags": ["test"],
        "source_chunk_ids": [1],
        "confidence": 0.5,
    })
    assert resp1.status_code == 422

    resp2 = await client.post("/ideas", json={
        "paper_id": paper_id,
        "title": "Valid Title",
        "summary": "",
        "research_question": "test",
        "method_hint": "test",
        "tags": ["test"],
        "source_chunk_ids": [1],
        "confidence": 0.5,
    })
    assert resp2.status_code == 422
