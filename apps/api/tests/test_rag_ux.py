"""Phase 26H: RAG UX improvement tests — evidence gate, low-confidence mode.

All tests mock LLM/embedding, never call real APIs.
Unit tests (TestRAGServiceEvidenceGate, TestMultiPaperRAGServiceEvidenceGate) do not require DB.
Integration tests (TestRAGUXIntegration) require a running DB; verified in Docker.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.main import app
from app.config import settings
from app.services.rag_service import RAGService, AnswerResult, RetrievedChunk, PaperNotFoundError
from app.services.multi_paper_rag_service import (
    MultiPaperRAGService, MultiPaperAnswerResult, MultiPaperRetrievedChunk,
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
        files={"file": ("rag_ux_test.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ============================================================
# Unit tests for RAGService.ask() with evidence gate
# ============================================================

class TestRAGServiceEvidenceGate:
    """Unit tests for RAGService evidence gate behavior."""

    @pytest.mark.asyncio
    async def test_strict_mode_low_confidence_returns_insufficient_context(self):
        """Strict mode: low confidence → insufficient_context with reason."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        low_score_chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="unrelated weather content", score=0.05,
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=low_score_chunks)

        result = await service.ask(paper_id=1, question="deep learning optimization")
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason == "score_below_threshold"
        assert result.retrieved_source_count == 1
        assert result.top_source_score == 0.05
        assert result.confidence == 0.05

    @pytest.mark.asyncio
    async def test_low_confidence_mode_with_sources_returns_answer(self):
        """allow_low_confidence_answer=true + source_count>0 → low_confidence_answer."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        low_score_chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="some content about models", score=0.05,
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=low_score_chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "Based on the fragments, models may refer to..."

        result = await service.ask(
            paper_id=1, question="deep learning optimization",
            allow_low_confidence_answer=True,
        )
        assert result.status == "low_confidence_answer"
        assert result.evidence_gate_reason == "score_below_threshold"
        assert result.retrieved_source_count == 1
        assert "低置信度" in result.answer
        assert result.confidence == 0.05

    @pytest.mark.asyncio
    async def test_no_chunks_even_with_low_confidence_still_refuses(self):
        """source_count=0 even with allow_low_confidence_answer=true → still refuse."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 0

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo

        result = await service.ask(
            paper_id=1, question="anything",
            allow_low_confidence_answer=True,
        )
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason == "no_chunks"
        assert result.retrieved_source_count == 0

    @pytest.mark.asyncio
    async def test_no_embeddings_returns_insufficient_context(self):
        """No embeddings → insufficient_context with reason."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 0

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo

        result = await service.ask(paper_id=1, question="test")
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason == "no_embeddings"

    @pytest.mark.asyncio
    async def test_no_retrieved_returns_insufficient_context(self):
        """No retrieved chunks → insufficient_context with reason."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=[])

        result = await service.ask(paper_id=1, question="test")
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason == "no_retrieved"

    @pytest.mark.asyncio
    async def test_evidence_below_threshold_strict_refuses(self):
        """Score above threshold but evidence overlap below → insufficient_context."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        medium_score_chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="weather patterns and climate data analysis", score=0.5,
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=medium_score_chunks)

        result = await service.ask(paper_id=1, question="quantum entanglement experiments")
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason == "evidence_below_threshold"

    @pytest.mark.asyncio
    async def test_evidence_below_threshold_low_confidence_allows(self):
        """Evidence below threshold + allow_low_confidence → low_confidence_answer."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        medium_score_chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="weather patterns and climate data analysis", score=0.5,
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=medium_score_chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "Based on limited context..."

        result = await service.ask(
            paper_id=1, question="quantum entanglement experiments",
            allow_low_confidence_answer=True,
        )
        assert result.status == "low_confidence_answer"
        assert result.evidence_gate_reason == "evidence_below_threshold"
        assert "低置信度" in result.answer

    @pytest.mark.asyncio
    async def test_answered_status_has_empty_gate_reason(self):
        """Normal answered status → evidence_gate_reason is empty."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        good_chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="Deep learning models achieve state of the art results in computer vision.",
                score=0.9,
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=good_chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "Deep learning models achieve SOTA."

        result = await service.ask(paper_id=1, question="What do deep learning models achieve?")
        assert result.status == "answered"
        assert result.evidence_gate_reason == ""
        assert result.retrieved_source_count == 1
        assert result.top_source_score == 0.9

    @pytest.mark.asyncio
    async def test_llm_failed_returns_insufficient_with_reason(self):
        """LLM failure → insufficient_context with llm_failed reason."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        good_chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="Deep learning models achieve state of the art results.",
                score=0.9,
            ),
        ]

        from app.services.ai_provider import ProviderRequestError

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=good_chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.side_effect = ProviderRequestError("API error")

        result = await service.ask(paper_id=1, question="What do deep learning models achieve?")
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason == "llm_failed"


# ============================================================
# Unit tests for MultiPaperRAGService.ask() with evidence gate
# ============================================================

class TestMultiPaperRAGServiceEvidenceGate:
    """Unit tests for MultiPaperRAGService evidence gate behavior."""

    @pytest.mark.asyncio
    async def test_strict_mode_low_confidence_returns_insufficient(self):
        """Strict mode: low confidence → insufficient_context."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_paper_ids.return_value = [1]
        mock_repo.get_paper.return_value = MagicMock(status="completed")

        low_score_chunks = [
            MultiPaperRetrievedChunk(
                paper_id=1, paper_title="Test", chunk_id=1, chunk_index=0,
                page_start=1, page_end=1,
                text_excerpt="unrelated content", score=0.05,
            ),
        ]

        service = MultiPaperRAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve_multi = AsyncMock(return_value=low_score_chunks)

        result = await service.ask(question="deep learning", paper_ids=[1])
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason == "score_below_threshold"

    @pytest.mark.asyncio
    async def test_low_confidence_mode_with_sources_returns_answer(self):
        """allow_low_confidence_answer=true + sources → low_confidence_answer."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_paper_ids.return_value = [1]
        mock_repo.get_paper.return_value = MagicMock(status="completed")

        low_score_chunks = [
            MultiPaperRetrievedChunk(
                paper_id=1, paper_title="Test", chunk_id=1, chunk_index=0,
                page_start=1, page_end=1,
                text_excerpt="some model content", score=0.05,
            ),
        ]

        service = MultiPaperRAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve_multi = AsyncMock(return_value=low_score_chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "Based on fragments..."

        result = await service.ask(
            question="deep learning", paper_ids=[1],
            allow_low_confidence_answer=True,
        )
        assert result.status == "low_confidence_answer"
        assert "低置信度" in result.answer

    @pytest.mark.asyncio
    async def test_no_eligible_papers_even_with_low_confidence_still_refuses(self):
        """No eligible papers → insufficient_context regardless of low_confidence flag."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_paper_ids.return_value = []
        mock_repo.get_paper.return_value = None

        service = MultiPaperRAGService(mock_session, user_id="test_user")
        service.repo = mock_repo

        result = await service.ask(
            question="anything", paper_ids=[99999],
            allow_low_confidence_answer=True,
        )
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason == "no_chunks"
        assert result.retrieved_source_count == 0


# ============================================================
# Integration tests via API endpoints
# ============================================================

class TestRAGUXIntegration:
    """Integration tests through FastAPI endpoints."""

    @pytest.mark.asyncio
    async def test_insufficient_context_includes_evidence_gate_reason(self, client: AsyncClient):
        """Unrelated question → insufficient_context with evidence_gate_reason in response."""
        pid = await _upload_paper(client, "Weather patterns and climate data analysis.")

        resp = await client.post(
            f"/papers/{pid}/ask",
            json={"question": "What is the recipe for chocolate cake?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "insufficient_context"
        assert data["evidence_gate_reason"] != ""
        assert data["retrieved_source_count"] >= 0
        assert isinstance(data["confidence"], float)

    @pytest.mark.asyncio
    async def test_low_confidence_answer_via_api(self, client: AsyncClient):
        """allow_low_confidence_answer=true → low_confidence_answer status in API."""
        pid = await _upload_paper(client, "Weather patterns and climate data analysis.")

        resp = await client.post(
            f"/papers/{pid}/ask",
            json={
                "question": "What is the recipe for chocolate cake?",
                "allow_low_confidence_answer": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # With local embedding, unrelated question may still be insufficient
        # if source_count=0, or low_confidence_answer if sources exist
        assert data["status"] in ("insufficient_context", "low_confidence_answer")
        if data["status"] == "low_confidence_answer":
            assert "低置信度" in data["answer"]
            assert data["evidence_gate_reason"] != ""

    @pytest.mark.asyncio
    async def test_multi_paper_low_confidence_answer_via_api(self, client: AsyncClient):
        """Multi-paper ask with allow_low_confidence_answer=true."""
        pid = await _upload_paper(client, "Weather patterns and climate data analysis.")

        resp = await client.post(
            "/papers/ask",
            json={
                "question": "What is the recipe for chocolate cake?",
                "paper_ids": [pid],
                "allow_low_confidence_answer": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("insufficient_context", "low_confidence_answer")

    @pytest.mark.asyncio
    async def test_ask_response_contains_new_fields(self, client: AsyncClient):
        """Response always contains evidence_gate_reason, retrieved_source_count, top_source_score."""
        pid = await _upload_paper(client, "Deep learning models for computer vision.")

        resp = await client.post(
            f"/papers/{pid}/ask",
            json={"question": "What do deep learning models achieve?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "evidence_gate_reason" in data
        assert "retrieved_source_count" in data
        assert "top_source_score" in data
        assert isinstance(data["retrieved_source_count"], int)
        assert isinstance(data["top_source_score"], float)

    @pytest.mark.asyncio
    async def test_multi_paper_ask_response_contains_new_fields(self, client: AsyncClient):
        """Multi-paper response contains new evidence gate fields."""
        pid = await _upload_paper(client, "Deep learning models for NLP tasks.")

        resp = await client.post(
            "/papers/ask",
            json={"question": "What do deep learning models achieve?", "paper_ids": [pid]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "evidence_gate_reason" in data
        assert "retrieved_source_count" in data
        assert "top_source_score" in data

    @pytest.mark.asyncio
    async def test_no_embedding_paper_ask_includes_reason(self, client: AsyncClient):
        """Paper with no embeddings → insufficient_context with reason."""
        pid = await _upload_paper(client, "Some content for testing.")

        async with _test_engine.begin() as conn:
            await conn.execute(
                text("UPDATE paper_chunks SET embedding = NULL WHERE paper_id = :pid"),
                {"pid": pid},
            )

        resp = await client.post(
            f"/papers/{pid}/ask",
            json={"question": "What is this?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "insufficient_context"
        assert data["evidence_gate_reason"] == "no_embeddings"

    @pytest.mark.asyncio
    async def test_low_confidence_answer_default_is_false(self, client: AsyncClient):
        """Default allow_low_confidence_answer is false — strict mode by default."""
        pid = await _upload_paper(client, "Weather patterns and climate data.")

        resp = await client.post(
            f"/papers/{pid}/ask",
            json={"question": "chocolate cake recipe"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should be insufficient_context, not low_confidence_answer
        assert data["status"] == "insufficient_context"
