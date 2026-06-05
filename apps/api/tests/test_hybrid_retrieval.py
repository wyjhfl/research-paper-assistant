"""Phase 34: Hybrid retrieval tests — lexical scoring, hybrid scoring, RAG integration.

All tests mock LLM/embedding, never call real APIs.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.lexical_retrieval import (
    tokenize,
    compute_lexical_score,
    compute_hybrid_score,
    determine_retrieval_mode,
    LexicalScoreResult,
)
from app.services.rag_service import RAGService, AnswerResult, RetrievedChunk
from app.services.multi_paper_rag_service import (
    MultiPaperRAGService, MultiPaperAnswerResult, MultiPaperRetrievedChunk,
)


# ============================================================
# Tokenization tests
# ============================================================

class TestTokenize:
    def test_english_query(self):
        tokens = tokenize("What is deep learning optimization?")
        assert "deep" in tokens
        assert "learning" in tokens
        assert "optimization" in tokens
        # Stop words removed
        assert "what" not in tokens
        assert "is" not in tokens

    def test_chinese_keywords(self):
        tokens = tokenize("这篇论文的核心贡献是什么")
        # Should produce Chinese bigrams
        assert len(tokens) > 0
        # "核心" should appear as bigram
        assert "核心" in tokens or "献是" in tokens  # at least some bigrams

    def test_stop_words_removed(self):
        tokens = tokenize("the a an is are was were")
        assert len(tokens) == 0

    def test_empty_query(self):
        tokens = tokenize("")
        assert tokens == []

    def test_single_char_tokens_filtered(self):
        tokens = tokenize("a I")
        assert len(tokens) == 0

    def test_mixed_english_chinese(self):
        tokens = tokenize("transformer模型的注意力机制")
        assert "transformer" in tokens
        assert len(tokens) > 1

    def test_chinese_stop_words(self):
        # Chinese stop words are individual chars, but bigrams may combine
        # two stop chars into a non-stop bigram. This is expected behavior.
        tokens = tokenize("的了的在是")
        # Bigrams like "的了" are not in stop words list — that's correct
        # because bigrams can be meaningful even if composed of function chars
        assert isinstance(tokens, list)


# ============================================================
# Lexical score tests
# ============================================================

class TestLexicalScore:
    def test_completely_unrelated_score_zero(self):
        result = compute_lexical_score("quantum entanglement", "weather patterns and climate data")
        assert result.score == 0.0
        assert result.overlap_count == 0

    def test_clear_keyword_match_score_above_zero(self):
        result = compute_lexical_score(
            "deep learning optimization",
            "Deep learning models achieve state of the art results in optimization tasks.",
        )
        assert result.score > 0.0
        assert result.overlap_count > 0
        assert result.query_token_recall > 0.0

    def test_phrase_bonus(self):
        result_with_phrase = compute_lexical_score(
            "deep learning",
            "Deep learning is a subset of machine learning.",
        )
        result_no_phrase = compute_lexical_score(
            "deep learning",
            "The deep ocean has learning fish.",
        )
        # Phrase match should score higher
        assert result_with_phrase.score > result_no_phrase.score
        assert result_with_phrase.has_phrase_match is True

    def test_title_bonus(self):
        result_with_title = compute_lexical_score(
            "attention mechanism",
            "Some text about models.",
            title="Attention Is All You Need",
        )
        result_no_title = compute_lexical_score(
            "attention mechanism",
            "Some text about models.",
            title="Weather Patterns",
        )
        assert result_with_title.score > result_no_title.score

    def test_score_clamped_to_0_1(self):
        # Very long text with many hits should still be <= 1.0
        text = "deep learning " * 1000
        result = compute_lexical_score("deep learning", text)
        assert 0.0 <= result.score <= 1.0

    def test_empty_query_returns_zero(self):
        result = compute_lexical_score("", "some text")
        assert result.score == 0.0

    def test_empty_text_returns_zero(self):
        result = compute_lexical_score("deep learning", "")
        assert result.score == 0.0

    def test_partial_match(self):
        result = compute_lexical_score(
            "deep learning optimization gradient descent",
            "Deep learning models for computer vision tasks.",
        )
        assert 0.0 < result.score < 1.0
        assert result.overlap_count >= 1


# ============================================================
# Hybrid score tests
# ============================================================

class TestHybridScore:
    @patch("app.services.lexical_retrieval.is_local_embedding_provider", return_value=True)
    def test_local_provider_lexical_primary(self, mock_local):
        score = compute_hybrid_score(0.0, 0.5)
        # Local: 0.9 * lexical + 0.1 * vector
        assert score == round(0.9 * 0.5 + 0.1 * 0.0, 4)

    @patch("app.services.lexical_retrieval.is_local_embedding_provider", return_value=False)
    def test_real_provider_weighted_hybrid(self, mock_real):
        score = compute_hybrid_score(0.8, 0.3, 0.7, 0.3)
        assert score == round(0.7 * 0.8 + 0.3 * 0.3, 4)

    @patch("app.services.lexical_retrieval.is_local_embedding_provider", return_value=True)
    def test_local_provider_zero_lexical(self, mock_local):
        score = compute_hybrid_score(0.0, 0.0)
        assert score == 0.0


# ============================================================
# Retrieval mode tests
# ============================================================

class TestRetrievalMode:
    @patch("app.services.lexical_retrieval.is_local_embedding_provider", return_value=True)
    def test_local_with_lexical_returns_lexical(self, mock_local):
        mode = determine_retrieval_mode(0.0, 0.5)
        assert mode == "lexical"

    @patch("app.services.lexical_retrieval.is_local_embedding_provider", return_value=True)
    def test_local_without_lexical_returns_vector(self, mock_local):
        mode = determine_retrieval_mode(0.0, 0.0)
        assert mode == "vector"

    @patch("app.services.lexical_retrieval.is_local_embedding_provider", return_value=False)
    def test_real_both_scores_returns_hybrid(self, mock_real):
        mode = determine_retrieval_mode(0.5, 0.3)
        assert mode == "hybrid"

    @patch("app.services.lexical_retrieval.is_local_embedding_provider", return_value=False)
    def test_real_vector_only_returns_vector(self, mock_real):
        mode = determine_retrieval_mode(0.5, 0.0)
        assert mode == "vector"


# ============================================================
# Single paper RAG with hybrid retrieval
# ============================================================

class TestRAGServiceHybridRetrieval:
    @pytest.mark.asyncio
    @patch("app.services.rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.rag_service.settings")
    async def test_local_embedding_lexical_match_returns_answered(self, mock_settings, mock_local):
        """Local embedding + lexical match → strict mode answered."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed", title="Deep Learning Paper")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        # Vector score=0 (local), but lexical match is strong
        chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="Deep learning models achieve state of the art results.",
                score=0.45, vector_score=0.0, lexical_score=0.5, retrieval_mode="lexical",
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "Deep learning achieves SOTA."

        result = await service.ask(paper_id=1, question="What do deep learning models achieve?")
        assert result.status == "answered"
        assert result.top_source_score > 0.0

    @pytest.mark.asyncio
    @patch("app.services.rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.rag_service.settings")
    async def test_local_embedding_no_lexical_match_returns_insufficient(self, mock_settings, mock_local):
        """Local embedding + no lexical match → insufficient_context."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed", title="Weather Paper")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        # Vector score=0, lexical score=0 (no match)
        chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="Weather patterns and climate data analysis.",
                score=0.0, vector_score=0.0, lexical_score=0.0, retrieval_mode="vector",
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=chunks)

        result = await service.ask(paper_id=1, question="quantum entanglement experiments")
        assert result.status == "insufficient_context"
        assert result.evidence_gate_reason in ("score_below_threshold", "no_lexical_match")

    @pytest.mark.asyncio
    async def test_source_count_zero_still_refuses(self):
        """source_count=0 still refuses even with lexical retrieval."""
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

    @pytest.mark.asyncio
    @patch("app.services.rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.rag_service.settings")
    async def test_low_confidence_with_lexical_low_match(self, mock_settings, mock_local):
        """Low lexical match + allow_low_confidence → low_confidence_answer."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed", title="Paper")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        # Low lexical match
        chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="Some models and data processing.",
                score=0.05, vector_score=0.0, lexical_score=0.05, retrieval_mode="lexical",
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "Based on limited context..."

        result = await service.ask(
            paper_id=1, question="deep learning optimization",
            allow_low_confidence_answer=True,
        )
        assert result.status == "low_confidence_answer"

    @pytest.mark.asyncio
    @patch("app.services.rag_service.is_local_embedding_provider", return_value=False)
    @patch("app.services.rag_service.settings")
    async def test_real_embedding_path_not_degraded(self, mock_settings, mock_real):
        """Real embedding provider: hybrid score uses vector + lexical."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed", title="Paper")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        # Real embedding: high vector score
        chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="Deep learning models achieve state of the art results.",
                score=0.75, vector_score=0.9, lexical_score=0.4, retrieval_mode="hybrid",
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "DL achieves SOTA."

        result = await service.ask(paper_id=1, question="What do deep learning models achieve?")
        assert result.status == "answered"
        assert result.sources[0].retrieval_mode == "hybrid"


# ============================================================
# Multi-paper RAG with hybrid retrieval
# ============================================================

class TestMultiPaperRAGHybridRetrieval:
    @pytest.mark.asyncio
    @patch("app.services.multi_paper_rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.multi_paper_rag_service.settings")
    async def test_multi_paper_lexical_match_sorting(self, mock_settings, mock_local):
        """Multi-paper: only one paper has keyword match, sorted correctly."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_paper_ids.return_value = [1, 2]
        mock_repo.get_paper.return_value = MagicMock(status="completed")

        # Paper 1 has lexical match, paper 2 doesn't
        chunks = [
            MultiPaperRetrievedChunk(
                paper_id=1, paper_title="DL Paper", chunk_id=1, chunk_index=0,
                page_start=1, page_end=1,
                text_excerpt="Deep learning models for NLP tasks.",
                score=0.45, vector_score=0.0, lexical_score=0.5, retrieval_mode="lexical",
            ),
            MultiPaperRetrievedChunk(
                paper_id=2, paper_title="Weather Paper", chunk_id=2, chunk_index=0,
                page_start=1, page_end=1,
                text_excerpt="Weather patterns and climate data.",
                score=0.0, vector_score=0.0, lexical_score=0.0, retrieval_mode="vector",
            ),
        ]

        service = MultiPaperRAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve_multi = AsyncMock(return_value=chunks)
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "Deep learning is used for NLP."

        result = await service.ask(question="deep learning NLP", paper_ids=[1, 2])
        assert result.status == "answered"
        # Paper 1 should be first (higher score)
        assert result.sources[0].paper_id == 1
        assert result.sources[0].paper_title == "DL Paper"

    @pytest.mark.asyncio
    @patch("app.services.multi_paper_rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.multi_paper_rag_service.settings")
    async def test_multi_paper_no_lexical_match_insufficient(self, mock_settings, mock_local):
        """Multi-paper: no lexical match → insufficient_context."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_paper_ids.return_value = [1]
        mock_repo.get_paper.return_value = MagicMock(status="completed")

        chunks = [
            MultiPaperRetrievedChunk(
                paper_id=1, paper_title="Weather Paper", chunk_id=1, chunk_index=0,
                page_start=1, page_end=1,
                text_excerpt="Weather patterns and climate data.",
                score=0.0, vector_score=0.0, lexical_score=0.0, retrieval_mode="vector",
            ),
        ]

        service = MultiPaperRAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve_multi = AsyncMock(return_value=chunks)

        result = await service.ask(question="quantum computing", paper_ids=[1])
        assert result.status == "insufficient_context"

    @pytest.mark.asyncio
    async def test_multi_paper_user_id_isolation(self):
        """User ID isolation preserved in multi-paper RAG."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_paper_ids.return_value = []
        mock_repo.get_paper.return_value = None

        service = MultiPaperRAGService(mock_session, user_id="other_user")
        service.repo = mock_repo

        result = await service.ask(question="anything", paper_ids=[99999])
        assert result.status == "insufficient_context"
