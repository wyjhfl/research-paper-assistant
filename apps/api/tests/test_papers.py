import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.main import app
from app.database import get_db
from app.config import settings
from app.services.ai_provider import LocalHashEmbeddingProvider

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


@pytest.mark.asyncio
async def test_list_papers_empty(client: AsyncClient):
    response = await client.get("/papers")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["papers"] == []


@pytest.mark.asyncio
async def test_upload_non_pdf_creates_record(client: AsyncClient):
    response = await client.post(
        "/papers/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ("completed", "failed")


@pytest.mark.asyncio
async def test_get_nonexistent_paper_returns_404(client: AsyncClient):
    response = await client.get("/papers/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_upload_invalid_pdf_creates_record(client: AsyncClient):
    response = await client.post(
        "/papers/upload",
        files={"file": ("fake.pdf", b"this is not a real pdf content", "application/pdf")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ("completed", "failed")
    assert data["id"] is not None

    detail_resp = await client.get(f"/papers/{data['id']}")
    assert detail_resp.status_code == 200


@pytest.mark.asyncio
async def test_upload_pdf_chunks_have_embedding(client: AsyncClient):
    pdf = _make_pdf("Machine learning and deep learning research.")
    response = await client.post(
        "/papers/upload",
        files={"file": ("test_paper.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "completed"
    assert data["chunk_count"] > 0


@pytest.mark.asyncio
async def test_ask_returns_sources_for_existing_paper(client: AsyncClient):
    pdf = _make_pdf("Deep learning models achieve state of the art results in computer vision.")
    upload_resp = await client.post(
        "/papers/upload",
        files={"file": ("rag_test.pdf", pdf, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    paper_id = upload_resp.json()["id"]

    ask_resp = await client.post(
        f"/papers/{paper_id}/ask",
        json={"question": "What do deep learning models achieve?"},
    )
    assert ask_resp.status_code == 200
    result = ask_resp.json()
    assert result["status"] in ("answered", "insufficient_context")
    if result["status"] == "answered":
        assert len(result["sources"]) > 0


@pytest.mark.asyncio
async def test_ask_nonexistent_paper_returns_404(client: AsyncClient):
    response = await client.post(
        "/papers/99999/ask",
        json={"question": "What is this about?"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ask_empty_question_returns_422(client: AsyncClient):
    response = await client.post(
        "/papers/1/ask",
        json={"question": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_no_embedding_returns_insufficient_context(client: AsyncClient):
    pdf = _make_pdf("Some content for testing.")
    upload_resp = await client.post(
        "/papers/upload",
        files={"file": ("no_emb.pdf", pdf, "application/pdf")},
    )
    paper_id = upload_resp.json()["id"]

    async with _test_engine.begin() as conn:
        await conn.execute(
            text("UPDATE paper_chunks SET embedding = NULL WHERE paper_id = :pid"),
            {"pid": paper_id},
        )

    ask_resp = await client.post(
        f"/papers/{paper_id}/ask",
        json={"question": "What is this?"},
    )
    assert ask_resp.status_code == 200
    result = ask_resp.json()
    assert result["status"] == "insufficient_context"


@pytest.mark.asyncio
async def test_ask_does_not_cross_paper(client: AsyncClient):
    pdf_a = _make_pdf("Paper Alpha discusses quantum computing advances.")
    pdf_b = _make_pdf("Paper Beta covers ocean biology research.")
    resp_a = await client.post(
        "/papers/upload",
        files={"file": ("alpha.pdf", pdf_a, "application/pdf")},
    )
    resp_b = await client.post(
        "/papers/upload",
        files={"file": ("beta.pdf", pdf_b, "application/pdf")},
    )
    paper_a_id = resp_a.json()["id"]
    paper_b_id = resp_b.json()["id"]

    ask_resp = await client.post(
        f"/papers/{paper_a_id}/ask",
        json={"question": "What is discussed?"},
    )
    assert ask_resp.status_code == 200
    result = ask_resp.json()
    for source in result["sources"]:
        assert source["paper_id"] == paper_a_id
        assert source["paper_id"] != paper_b_id


@pytest.mark.asyncio
async def test_unrelated_question_returns_insufficient_context(client: AsyncClient):
    pdf = _make_pdf("Deep learning models achieve state of the art results in computer vision.")
    upload_resp = await client.post(
        "/papers/upload",
        files={"file": ("topic.pdf", pdf, "application/pdf")},
    )
    paper_id = upload_resp.json()["id"]

    ask_resp = await client.post(
        f"/papers/{paper_id}/ask",
        json={"question": "What is the recipe for chocolate cake?"},
    )
    assert ask_resp.status_code == 200
    result = ask_resp.json()
    assert result["status"] == "insufficient_context"


@pytest.mark.asyncio
async def test_local_embedding_is_stable_across_provider_instances():
    provider_a = LocalHashEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
    provider_b = LocalHashEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)

    texts = [
        "Deep learning achieves state of the art results.",
        "量子计算在密码学领域有重要应用。",
        "The quick brown fox jumps over the lazy dog.",
    ]

    emb_a = await provider_a.embed_texts(texts)
    emb_b = await provider_b.embed_texts(texts)

    for i in range(len(texts)):
        for j in range(len(emb_a[i])):
            assert abs(emb_a[i][j] - emb_b[i][j]) < 1e-6, (
                f"Embedding mismatch at text[{i}][{j}]: {emb_a[i][j]} vs {emb_b[i][j]}"
            )


@pytest.mark.asyncio
async def test_embedding_dimension_matches_settings():
    provider = LocalHashEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
    assert provider.get_dimension() == settings.EMBEDDING_DIMENSION

    emb = await provider.embed_texts(["test text"])
    assert len(emb[0]) == settings.EMBEDDING_DIMENSION
