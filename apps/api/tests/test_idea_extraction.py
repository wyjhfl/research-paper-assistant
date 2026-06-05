"""Phase 27L/29: Idea extraction tests — heuristic-first + LLM fallback.

Heuristic is conservative: only returns ideas when text contains explicit
research clue keywords (limitation, future work, open problem, etc.).
LLM fallback is reachable when heuristic returns 0.

All tests mock LLM/embedding, never call real APIs.
Unit tests do not require DB. Integration tests require DB; verified in Docker.
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.config import settings
from app.services.idea_service import IdeaService, IdeaCandidate, ExtractIdeasResult, CrossPaperIdea
from app.services.ai_provider import (
    ProviderRequestError, ProviderConfigurationError, ProviderResponseError,
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


async def _upload_paper(client: AsyncClient, text: str, filename: str = "idea_test.pdf") -> int:
    pdf = _make_pdf(text)
    resp = await client.post(
        "/papers/upload",
        files={"file": (filename, pdf, "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ============================================================
# Unit tests for IdeaService._heuristic_ideas (conservative)
# ============================================================

class TestHeuristicIdeas:
    """Test conservative heuristic idea extraction."""

    def test_chunk_with_limitation_returns_idea(self):
        """Chunk containing 'limitation' → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=10, text="One limitation of this approach is the lack of scalability.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1
        assert candidates[0].extraction_method == "heuristic"
        assert candidates[0].source_chunk_ids == [10]
        assert "limitation" in candidates[0].tags

    def test_chunk_with_future_work_returns_idea(self):
        """Chunk containing 'future work' → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=11, text="For future work, we plan to extend this to multi-modal settings.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1
        assert "future-work" in candidates[0].tags

    def test_chunk_with_open_problem_returns_idea(self):
        """Chunk containing 'open problem' → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=12, text="This remains an open problem in the field.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1

    def test_chunk_with_challenge_returns_idea(self):
        """Chunk containing 'challenge' → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=13, text="A key challenge is balancing accuracy and efficiency.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1

    def test_chunk_with_propose_returns_idea(self):
        """Chunk containing 'propose' → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=14, text="We propose a novel method for attention computation.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1

    def test_chunk_with_improve_returns_idea(self):
        """Chunk containing 'improve' → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=15, text="This can improve the training speed by 2x.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1

    def test_chunk_with_extend_returns_idea(self):
        """Chunk containing 'extend' → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=16, text="We extend the previous work to handle long sequences.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1

    def test_chunk_with_direction_returns_idea(self):
        """Chunk containing 'direction' → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=17, text="A promising direction is to combine retrieval with generation.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1

    def test_chunk_with_chinese_clue_returns_idea(self):
        """Chunk containing Chinese research clue → heuristic returns idea."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=18, text="本文的局限在于数据集规模有限。")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1

    def test_plain_chunk_returns_no_idea(self):
        """Plain chunk without research clues → heuristic returns empty."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=20, text="The weather is sunny today and the temperature is 25 degrees.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 0

    def test_method_description_chunk_returns_no_idea(self):
        """Method description without research clues → heuristic returns empty."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=21, text="We use a transformer architecture with 12 layers and 8 attention heads.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 0

    def test_short_abstract_returns_no_idea(self):
        """Short abstract without clues → heuristic returns empty."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=22, text="This paper presents a system for document analysis.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 0

    def test_empty_chunks_returns_empty(self):
        """No chunks → heuristic returns empty list."""
        service = IdeaService(AsyncMock())
        candidates = service._heuristic_ideas([], "Test Paper")
        assert len(candidates) == 0

    def test_multiple_chunks_with_clues_returns_up_to_3(self):
        """Multiple chunks with clues → up to 3 ideas."""
        service = IdeaService(AsyncMock())
        chunks = [
            MagicMock(id=i, text=f"Chunk {i}: a limitation of approach {i}.")
            for i in range(5)
        ]
        candidates = service._heuristic_ideas(chunks, "Test Paper")
        assert len(candidates) == 3
        # Each should reference its own chunk id
        assert candidates[0].source_chunk_ids == [0]
        assert candidates[1].source_chunk_ids == [1]
        assert candidates[2].source_chunk_ids == [2]

    def test_mixed_chunks_only_matching_return_ideas(self):
        """Mix of clue and non-clue chunks → only clue chunks produce ideas."""
        service = IdeaService(AsyncMock())
        chunks = [
            MagicMock(id=1, text="The model achieves 95% accuracy on the benchmark."),
            MagicMock(id=2, text="A key challenge is generalizing to unseen domains."),
            MagicMock(id=3, text="The dataset contains 10,000 samples."),
        ]
        candidates = service._heuristic_ideas(chunks, "Test Paper")
        assert len(candidates) == 1
        assert candidates[0].source_chunk_ids == [2]

    def test_confidence_is_conservative(self):
        """Heuristic confidence should be 0.4 (conservative)."""
        service = IdeaService(AsyncMock())
        mock_chunk = MagicMock(id=10, text="One limitation of this approach is scalability.")
        candidates = service._heuristic_ideas([mock_chunk], "Test Paper")
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.4


# ============================================================
# Unit tests for IdeaService._parse_ideas
# ============================================================

class TestIdeaParsing:
    """Test LLM output parsing for idea extraction."""

    def test_parse_valid_json_ideas(self):
        """Valid JSON array → parsed ideas with extraction_method=llm_fallback."""
        service = IdeaService(AsyncMock())
        raw = json.dumps([
            {
                "title": "Novel Attention Mechanism",
                "summary": "A new attention mechanism for transformers",
                "research_question": "Can sparse attention improve efficiency?",
                "method_hint": "Modify attention weights with sparsity constraint",
                "tags": ["attention", "efficiency"],
                "confidence": 0.8,
            }
        ])
        candidates = service._parse_ideas(raw, extraction_method="llm_fallback")
        assert len(candidates) == 1
        assert candidates[0].title == "Novel Attention Mechanism"
        assert candidates[0].extraction_method == "llm_fallback"
        assert candidates[0].confidence == 0.8

    def test_parse_invalid_json_returns_empty(self):
        """Invalid JSON → empty list, no fake candidates."""
        service = IdeaService(AsyncMock())
        raw = "This is not valid JSON at all"
        candidates = service._parse_ideas(raw, extraction_method="llm_fallback")
        assert len(candidates) == 0

    def test_parse_empty_json_array(self):
        """Empty JSON array → no candidates."""
        service = IdeaService(AsyncMock())
        raw = "[]"
        candidates = service._parse_ideas(raw, extraction_method="llm_fallback")
        assert len(candidates) == 0

    def test_parse_json_with_ideas_key(self):
        """JSON with 'ideas' key → parsed correctly."""
        service = IdeaService(AsyncMock())
        raw = json.dumps({"ideas": [{"title": "Test", "summary": "S", "research_question": "Q", "method_hint": "M", "tags": [], "confidence": 0.6}]})
        candidates = service._parse_ideas(raw, extraction_method="llm_fallback")
        assert len(candidates) == 1

    def test_parse_limits_to_5_ideas(self):
        """More than 5 ideas → truncated to 5."""
        service = IdeaService(AsyncMock())
        ideas = [{"title": f"Idea {i}", "summary": "S", "research_question": "Q", "method_hint": "M", "tags": [], "confidence": 0.5} for i in range(10)]
        candidates = service._parse_ideas(json.dumps(ideas), extraction_method="llm_fallback")
        assert len(candidates) == 5

    def test_parse_skips_empty_title(self):
        """Items with empty title are skipped."""
        service = IdeaService(AsyncMock())
        raw = json.dumps([
            {"title": "", "summary": "No title", "research_question": "Q", "method_hint": "M", "tags": [], "confidence": 0.5},
            {"title": "Valid", "summary": "Has title", "research_question": "Q", "method_hint": "M", "tags": [], "confidence": 0.5},
        ])
        candidates = service._parse_ideas(raw, extraction_method="llm_fallback")
        assert len(candidates) == 1
        assert candidates[0].title == "Valid"

    def test_parse_clamps_confidence(self):
        """Confidence > 1 or < 0 is clamped."""
        service = IdeaService(AsyncMock())
        raw = json.dumps([
            {"title": "High", "summary": "S", "research_question": "Q", "method_hint": "M", "tags": [], "confidence": 2.5},
            {"title": "Low", "summary": "S", "research_question": "Q", "method_hint": "M", "tags": [], "confidence": -0.5},
        ])
        candidates = service._parse_ideas(raw, extraction_method="llm_fallback")
        assert candidates[0].confidence == 1.0
        assert candidates[1].confidence == 0.0

    def test_parse_cleans_tags(self):
        """Non-string tags are filtered; bool excluded; non-list becomes empty."""
        service = IdeaService(AsyncMock())
        raw = json.dumps([
            {"title": "Mixed", "summary": "S", "research_question": "Q", "method_hint": "M", "tags": ["valid", 123, None, True], "confidence": 0.5},
            {"title": "Bad", "summary": "S", "research_question": "Q", "method_hint": "M", "tags": "not a list", "confidence": 0.5},
        ])
        candidates = service._parse_ideas(raw, extraction_method="llm_fallback")
        assert candidates[0].tags == ["valid", "123"]
        assert candidates[1].tags == []

    def test_parse_non_list_data_returns_empty(self):
        """If parsed JSON is a string (not list/dict), returns empty."""
        service = IdeaService(AsyncMock())
        raw = json.dumps("just a string")
        candidates = service._parse_ideas(raw, extraction_method="llm_fallback")
        assert len(candidates) == 0


# ============================================================
# Unit tests for IdeaService._parse_cross_paper_ideas
# ============================================================

class TestCrossPaperIdeaParsing:
    """Test cross-paper idea parsing."""

    def test_parse_valid_cross_paper_ideas(self):
        service = IdeaService(AsyncMock())
        raw = json.dumps([{"title": "Cross-domain", "summary": "S", "motivation": "M", "involved_paper_ids": [1, 2], "confidence": 0.7}])
        ideas = service._parse_cross_paper_ideas(raw, paper_ids=[1, 2], max_ideas=3)
        assert len(ideas) == 1
        assert ideas[0].involved_paper_ids == [1, 2]

    def test_parse_invalid_json_returns_empty(self):
        service = IdeaService(AsyncMock())
        ideas = service._parse_cross_paper_ideas("not json", paper_ids=[1, 2], max_ideas=3)
        assert len(ideas) == 0

    def test_parse_filters_invalid_paper_ids(self):
        service = IdeaService(AsyncMock())
        raw = json.dumps([{"title": "T", "summary": "S", "motivation": "M", "involved_paper_ids": [99, 100], "confidence": 0.5}])
        ideas = service._parse_cross_paper_ideas(raw, paper_ids=[1, 2], max_ideas=3)
        assert ideas[0].involved_paper_ids == [1, 2]

    def test_parse_skips_empty_title(self):
        service = IdeaService(AsyncMock())
        raw = json.dumps([
            {"title": "", "summary": "S", "motivation": "M", "involved_paper_ids": [1], "confidence": 0.5},
            {"title": "Valid", "summary": "S", "motivation": "M", "involved_paper_ids": [1], "confidence": 0.5},
        ])
        ideas = service._parse_cross_paper_ideas(raw, paper_ids=[1, 2], max_ideas=3)
        assert len(ideas) == 1


# ============================================================
# Unit tests for IdeaService.extract_ideas — heuristic-first + LLM fallback
# ============================================================

class TestExtractIdeasHeuristicFirst:
    """Test extract_ideas: heuristic-first, LLM fallback when heuristic=0."""

    @pytest.mark.asyncio
    async def test_heuristic_has_results_does_not_call_llm(self):
        """Heuristic returns results → no LLM call, extraction_method=heuristic."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        # Chunk with research clue → heuristic will match
        mock_chunk = MagicMock(id=10, text="One limitation of this approach is the lack of scalability.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        with patch("app.services.idea_service.get_llm_provider") as mock_get_llm:
            result = await service.extract_ideas(paper_id=1, user_id="test_user")
            mock_get_llm.assert_not_called()

        assert len(result.candidates) >= 1
        assert result.extraction_method == "heuristic"
        assert result.candidates[0].extraction_method == "heuristic"

    @pytest.mark.asyncio
    async def test_plain_chunk_no_heuristic_fallback_enabled_calls_llm(self):
        """Plain chunk (no clue) + fallback enabled → calls LLM mock."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        # Plain chunk without research clues → heuristic returns 0
        mock_chunk = MagicMock(id=10, text="The weather is sunny today.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        mock_rag = AsyncMock()
        mock_rag_result = MagicMock()
        mock_rag_result.sources = [MagicMock(text_excerpt="context about research")]
        mock_rag.ask.return_value = mock_rag_result

        mock_llm = AsyncMock()
        mock_llm.generate_answer.return_value = json.dumps([
            {"title": "Novel Method", "summary": "A new approach", "research_question": "How?",
             "method_hint": "Use attention", "tags": ["dl"], "confidence": 0.8}
        ])

        with patch("app.services.idea_service.RAGService", return_value=mock_rag), \
             patch("app.services.idea_service.get_llm_provider", return_value=mock_llm):
            result = await service.extract_ideas(
                paper_id=1, user_id="test_user", use_llm_fallback=True,
            )

        assert len(result.candidates) >= 1
        assert result.extraction_method == "llm_fallback"
        assert result.candidates[0].extraction_method == "llm_fallback"

    @pytest.mark.asyncio
    async def test_plain_chunk_fallback_disabled_returns_reason(self):
        """Plain chunk (no clue) + fallback disabled → returns reason, no LLM."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_chunk = MagicMock(id=10, text="The weather is sunny today.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        with patch("app.services.idea_service.get_llm_provider") as mock_get_llm:
            result = await service.extract_ideas(
                paper_id=1, user_id="test_user", use_llm_fallback=False,
            )
            mock_get_llm.assert_not_called()

        assert len(result.candidates) == 0
        assert result.reason != ""
        assert len(result.suggestions) >= 1
        assert result.extraction_method == "heuristic"

    @pytest.mark.asyncio
    async def test_llm_invalid_json_returns_reason_no_fake_candidate(self):
        """LLM returns invalid JSON → 0 ideas + reason, no fake candidate."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_chunk = MagicMock(id=10, text="The weather is sunny today.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        mock_rag = AsyncMock()
        mock_rag_result = MagicMock()
        mock_rag_result.sources = [MagicMock(text_excerpt="context")]
        mock_rag.ask.return_value = mock_rag_result

        mock_llm = AsyncMock()
        mock_llm.generate_answer.return_value = "This is not JSON at all."

        with patch("app.services.idea_service.RAGService", return_value=mock_rag), \
             patch("app.services.idea_service.get_llm_provider", return_value=mock_llm):
            result = await service.extract_ideas(
                paper_id=1, user_id="test_user", use_llm_fallback=True,
            )

        assert len(result.candidates) == 0
        assert result.reason != ""
        assert "解析失败" in result.reason or "LLM" in result.reason
        assert result.extraction_method == "llm_fallback"

    @pytest.mark.asyncio
    async def test_provider_configuration_error_no_unbound(self):
        """ProviderConfigurationError → safe failure, no UnboundLocalError."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_chunk = MagicMock(id=10, text="The weather is sunny today.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        mock_rag = AsyncMock()
        mock_rag_result = MagicMock()
        mock_rag_result.sources = [MagicMock(text_excerpt="context")]
        mock_rag.ask.return_value = mock_rag_result

        mock_llm = AsyncMock()
        mock_llm.generate_answer.side_effect = ProviderConfigurationError("Not configured")

        with patch("app.services.idea_service.RAGService", return_value=mock_rag), \
             patch("app.services.idea_service.get_llm_provider", return_value=mock_llm):
            result = await service.extract_ideas(
                paper_id=1, user_id="test_user", use_llm_fallback=True,
            )

        assert len(result.candidates) == 0
        assert result.reason != ""

    @pytest.mark.asyncio
    async def test_provider_request_error_safe_failure(self):
        """ProviderRequestError → safe failure."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_chunk = MagicMock(id=10, text="The weather is sunny today.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        mock_rag = AsyncMock()
        mock_rag_result = MagicMock()
        mock_rag_result.sources = [MagicMock(text_excerpt="context")]
        mock_rag.ask.return_value = mock_rag_result

        mock_llm = AsyncMock()
        mock_llm.generate_answer.side_effect = ProviderRequestError("API error")

        with patch("app.services.idea_service.RAGService", return_value=mock_rag), \
             patch("app.services.idea_service.get_llm_provider", return_value=mock_llm):
            result = await service.extract_ideas(
                paper_id=1, user_id="test_user", use_llm_fallback=True,
            )

        assert len(result.candidates) == 0
        assert result.reason != ""

    @pytest.mark.asyncio
    async def test_provider_response_error_safe_failure(self):
        """ProviderResponseError → safe failure."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_chunk = MagicMock(id=10, text="The weather is sunny today.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        mock_rag = AsyncMock()
        mock_rag_result = MagicMock()
        mock_rag_result.sources = [MagicMock(text_excerpt="context")]
        mock_rag.ask.return_value = mock_rag_result

        mock_llm = AsyncMock()
        mock_llm.generate_answer.side_effect = ProviderResponseError("Bad response")

        with patch("app.services.idea_service.RAGService", return_value=mock_rag), \
             patch("app.services.idea_service.get_llm_provider", return_value=mock_llm):
            result = await service.extract_ideas(
                paper_id=1, user_id="test_user", use_llm_fallback=True,
            )

        assert len(result.candidates) == 0
        assert result.reason != ""

    @pytest.mark.asyncio
    async def test_no_chunks_returns_reason_and_suggestions(self):
        """No chunks → reason + suggestions, no LLM call."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_repo.get_chunks_by_paper.return_value = []

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        with patch("app.services.idea_service.get_llm_provider") as mock_get_llm:
            result = await service.extract_ideas(paper_id=1, user_id="test_user")
            mock_get_llm.assert_not_called()

        assert len(result.candidates) == 0
        assert result.reason != ""
        assert len(result.suggestions) >= 1

    @pytest.mark.asyncio
    async def test_idea_sources_traceable(self):
        """Heuristic ideas have source_chunk_ids referencing real chunk ids."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_chunk = MagicMock(id=42, text="One limitation of this approach is scalability.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        result = await service.extract_ideas(paper_id=1, user_id="test_user")
        assert len(result.candidates) >= 1
        assert 42 in result.candidates[0].source_chunk_ids

    @pytest.mark.asyncio
    async def test_max_ideas_limits_output(self):
        """max_ideas parameter limits the number of returned candidates."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        chunks = [MagicMock(id=i, text=f"Chunk {i}: a limitation of method {i}.") for i in range(5)]
        mock_repo.get_chunks_by_paper.return_value = chunks

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        result = await service.extract_ideas(paper_id=1, user_id="test_user", max_ideas=1)
        assert len(result.candidates) <= 1

    @pytest.mark.asyncio
    async def test_user_id_isolation_preserved(self):
        """Paper not found for different user_id → ValueError."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = None

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        with pytest.raises(ValueError, match="not found"):
            await service.extract_ideas(paper_id=1, user_id="other_user")

    @pytest.mark.asyncio
    async def test_llm_fallback_extraction_method_is_llm_fallback(self):
        """LLM fallback candidates have extraction_method=llm_fallback."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_chunk = MagicMock(id=10, text="The weather is sunny today.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        mock_rag = AsyncMock()
        mock_rag_result = MagicMock()
        mock_rag_result.sources = [MagicMock(text_excerpt="context")]
        mock_rag.ask.return_value = mock_rag_result

        mock_llm = AsyncMock()
        mock_llm.generate_answer.return_value = json.dumps([
            {"title": "Test", "summary": "S", "research_question": "Q", "method_hint": "M", "tags": [], "confidence": 0.7}
        ])

        with patch("app.services.idea_service.RAGService", return_value=mock_rag), \
             patch("app.services.idea_service.get_llm_provider", return_value=mock_llm):
            result = await service.extract_ideas(paper_id=1, user_id="test_user", use_llm_fallback=True)

        assert result.extraction_method == "llm_fallback"
        for c in result.candidates:
            assert c.extraction_method == "llm_fallback"

    @pytest.mark.asyncio
    async def test_heuristic_extraction_method_is_heuristic(self):
        """Heuristic candidates have extraction_method=heuristic."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        paper = MagicMock(status="completed", title="Test Paper")
        mock_repo.get_paper.return_value = paper
        mock_chunk = MagicMock(id=10, text="One limitation of this approach is scalability.")
        mock_repo.get_chunks_by_paper.return_value = [mock_chunk]

        service = IdeaService(mock_session)
        service.paper_repo = mock_repo

        result = await service.extract_ideas(paper_id=1, user_id="test_user")
        assert result.extraction_method == "heuristic"
        for c in result.candidates:
            assert c.extraction_method == "heuristic"


# ============================================================
# Integration tests via API endpoints (require DB)
# ============================================================

class TestIdeaExtractionIntegration:
    """Integration tests through FastAPI endpoints. Verified in Docker."""

    @pytest.mark.asyncio
    async def test_extract_ideas_includes_extraction_method(self, client: AsyncClient):
        """Extract ideas response includes extraction_method field."""
        paper_id = await _upload_paper(
            client,
            "This paper proposes a novel method for deep learning optimization. "
            "Future work includes exploring sparse attention mechanisms.",
        )
        resp = await client.post(f"/papers/{paper_id}/ideas/extract")
        assert resp.status_code == 200
        data = resp.json()
        assert "extraction_method" in data
        assert data["extraction_method"] in ("heuristic", "llm_fallback", "")

    @pytest.mark.asyncio
    async def test_extract_ideas_candidates_have_extraction_method(self, client: AsyncClient):
        """Each candidate in response has extraction_method."""
        paper_id = await _upload_paper(
            client,
            "This paper discusses limitations of current NLP models and future directions.",
        )
        resp = await client.post(f"/papers/{paper_id}/ideas/extract")
        assert resp.status_code == 200
        data = resp.json()
        for c in data["candidates"]:
            assert "extraction_method" in c
            assert c["extraction_method"] in ("heuristic", "llm_fallback")

    @pytest.mark.asyncio
    async def test_extract_ideas_with_use_llm_fallback_param(self, client: AsyncClient):
        """use_llm_fallback query parameter is accepted."""
        paper_id = await _upload_paper(
            client,
            "This paper proposes a novel method for optimization.",
        )
        resp = await client.post(
            f"/papers/{paper_id}/ideas/extract",
            params={"use_llm_fallback": "true", "max_ideas": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) <= 2

    @pytest.mark.asyncio
    async def test_cross_paper_synthesize_endpoint(self, client: AsyncClient):
        """POST /papers/ideas/synthesize returns cross-paper ideas."""
        pid1 = await _upload_paper(client, "Paper about neural network limitations.", "nn.pdf")
        pid2 = await _upload_paper(client, "Paper about optimization challenges.", "opt.pdf")

        resp = await client.post(
            "/papers/ideas/synthesize",
            json={"paper_ids": [pid1, pid2], "max_ideas": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ideas" in data

    @pytest.mark.asyncio
    async def test_cross_paper_synthesize_nonexistent_paper_returns_404(self, client: AsyncClient):
        resp = await client.post(
            "/papers/ideas/synthesize",
            json={"paper_ids": [99998, 99999], "max_ideas": 2},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_paper_synthesize_requires_at_least_2_papers(self, client: AsyncClient):
        pid = await _upload_paper(client, "Single paper content.", "single.pdf")
        resp = await client.post(
            "/papers/ideas/synthesize",
            json={"paper_ids": [pid], "max_ideas": 2},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_user_isolation_in_idea_extraction(self, client: AsyncClient):
        """Ideas saved for one user are not visible to another."""
        paper_id = await _upload_paper(
            client,
            "This paper discusses limitations of current approaches and future work.",
        )

        extract_resp = await client.post(f"/papers/{paper_id}/ideas/extract")
        assert extract_resp.status_code == 200
        candidates = extract_resp.json()["candidates"]

        if candidates:
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

            other_resp = await client.get("/ideas", headers={"X-User-Id": "other_user"})
            assert other_resp.status_code == 200
            other_data = other_resp.json()
            assert not any(i["title"] == c["title"] for i in other_data["ideas"])
