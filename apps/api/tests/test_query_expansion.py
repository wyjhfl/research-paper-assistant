"""Phase 38: Cross-language query expansion tests.

All tests are purely local — no real LLM/embedding API calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.query_expansion import (
    expand_query,
    _contains_chinese,
    _extract_chinese_terms,
    QueryExpansionResult,
    should_expand_query,
)


# ============================================================
# Chinese detection tests
# ============================================================

class TestChineseDetection:
    def test_pure_chinese(self):
        assert _contains_chinese("这篇论文的核心贡献是什么") is True

    def test_mixed_chinese_english(self):
        assert _contains_chinese("transformer模型的注意力机制") is True

    def test_pure_english(self):
        assert _contains_chinese("What is the main contribution?") is False

    def test_numbers_and_symbols(self):
        assert _contains_chinese("1234 !@#$") is False

    def test_empty_string(self):
        assert _contains_chinese("") is False

    def test_japanese_not_detected_as_chinese(self):
        # Japanese hiragana/katakana are outside \u4e00-\u9fff
        assert _contains_chinese("こんにちは") is False


class TestExtractChineseTerms:
    def test_extract_from_mixed(self):
        terms = _extract_chinese_terms("这篇论文的核心贡献是什么")
        assert len(terms) > 0
        # Should contain continuous Chinese sequences
        combined = "".join(terms)
        assert "核心" in combined or "贡献" in combined

    def test_no_chinese(self):
        terms = _extract_chinese_terms("hello world")
        assert terms == []

    def test_mixed_text(self):
        terms = _extract_chinese_terms("关于RAG的检索增强生成")
        combined = "".join(terms)
        assert "检索增强" in combined or "生成" in combined


# ============================================================
# Query expansion core tests
# ============================================================

class TestExpandQuery:
    def test_chinese_core_contribution(self):
        """中文'核心贡献'扩展为 contribution / core / main idea."""
        result = expand_query("这篇论文的核心贡献是什么")
        assert result.applied is True
        assert result.reason == "chinese_query_expanded"
        assert "core" in result.expanded_terms
        assert "contribution" in result.expanded_terms

    def test_chinese_limitation(self):
        """中文'局限'扩展为 limitation / weakness / challenge."""
        result = expand_query("这篇论文有什么局限")
        assert result.applied is True
        assert "limitation" in result.expanded_terms

    def test_chinese_attention(self):
        """中文'注意力'扩展为 attention / transformer."""
        result = expand_query("注意力机制")
        assert result.applied is True
        assert "attention" in result.expanded_terms

    def test_chinese_method(self):
        """中文'方法'扩展为 method / approach / framework."""
        result = expand_query("这篇论文的方法是什么")
        assert result.applied is True
        assert "method" in result.expanded_terms

    def test_chinese_future_work(self):
        """中文'未来工作'扩展为 future work / direction / improve."""
        result = expand_query("未来工作方向")
        assert result.applied is True
        assert "future work" in result.expanded_terms or "direction" in result.expanded_terms

    def test_chinese_multi_agent(self):
        """中文'多智能体'扩展为 multi-agent / agent / workflow."""
        result = expand_query("多智能体系统")
        assert result.applied is True
        assert "multi-agent" in result.expanded_terms

    def test_chinese_retrieval_augmented(self):
        """中文'检索增强'扩展为 retrieval / augmented / RAG."""
        result = expand_query("检索增强生成")
        assert result.applied is True
        assert "retrieval" in result.expanded_terms or "RAG" in result.expanded_terms

    def test_english_not_expanded(self):
        """英文 query 不扩展."""
        result = expand_query("What is the main contribution of this paper?")
        assert result.applied is False
        assert result.reason == "no_chinese"
        assert result.expanded_terms == []
        assert result.expanded_query == "What is the main contribution of this paper?"

    def test_empty_query_not_expanded(self):
        """空 query 不扩展."""
        result = expand_query("")
        assert result.applied is False
        assert result.reason == "empty_query"

    def test_whitespace_only_not_expanded(self):
        """纯空格 query 不扩展."""
        result = expand_query("   ")
        assert result.applied is False
        assert result.reason == "empty_query"

    def test_chinese_no_matching_terms(self):
        """中文 query 但词典无匹配项时不扩展."""
        result = expand_query("你好世界")
        # "你好" and "世界" are not in the academic dictionary
        assert result.applied is False
        assert result.reason == "no_matching_terms"

    def test_expanded_query_contains_original(self):
        """扩展后 query 包含原始 query."""
        original = "这篇论文的核心贡献是什么"
        result = expand_query(original)
        assert result.original_query == original
        assert result.expanded_query.startswith(original)

    def test_expanded_terms_are_lowercase(self):
        """扩展词全部小写."""
        result = expand_query("核心贡献")
        for term in result.expanded_terms:
            assert term == term.lower()

    def test_no_duplicate_expanded_terms(self):
        """扩展词无重复."""
        result = expand_query("核心贡献贡献")
        # "贡献" appears twice but should only be expanded once
        assert len(result.expanded_terms) == len(set(result.expanded_terms))

    def test_longest_match_first(self):
        """长词优先匹配：'核心贡献' 不应拆成 '核心' + '贡献'."""
        result = expand_query("核心贡献")
        # "核心贡献" is in the map, should match as whole
        assert "core" in result.expanded_terms
        assert "contribution" in result.expanded_terms
        assert "main contribution" in result.expanded_terms

    def test_attention_mechanism_long_match(self):
        """'注意力机制' 优先于 '注意力' + '机制'."""
        result = expand_query("注意力机制")
        # "注意力机制" is in the map as a longer entry
        assert "attention mechanism" in result.expanded_terms

    def test_result_dataclass_fields(self):
        """QueryExpansionResult dataclass 字段完整."""
        result = expand_query("核心贡献")
        assert hasattr(result, "original_query")
        assert hasattr(result, "expanded_query")
        assert hasattr(result, "expanded_terms")
        assert hasattr(result, "applied")
        assert hasattr(result, "reason")

    def test_chinese_improve(self):
        """中文'改进'扩展为 improve / extend / enhance."""
        result = expand_query("如何改进")
        assert result.applied is True
        assert "improve" in result.expanded_terms

    def test_chinese_experiment(self):
        """中文'实验'扩展为 experiment / evaluation / result."""
        result = expand_query("实验结果")
        assert result.applied is True
        assert "experiment" in result.expanded_terms or "result" in result.expanded_terms

    def test_should_expand_query_requires_enabled_static_mode(self):
        assert should_expand_query(True, "static") is True
        assert should_expand_query(True, " STATIC ") is True
        assert should_expand_query(False, "static") is False
        assert should_expand_query(True, "llm") is False


# ============================================================
# Lexical score with expansion integration
# ============================================================

class TestLexicalScoreWithExpansion:
    def test_chinese_query_english_chunk_score_improves(self):
        """中文 query 对英文 chunk lexical_score 从 0 变为 > 0."""
        from app.services.lexical_retrieval import compute_lexical_score, compute_lexical_score_with_expansion

        query = "这篇论文的核心贡献是什么"
        chunk_text = "The main contribution of this paper is a novel method for attention mechanism."
        title = "Attention Is All You Need"

        # Without expansion: Chinese bigrams cannot match English text
        result_no_exp = compute_lexical_score(query, chunk_text, title)
        assert result_no_exp.score == 0.0

        # With expansion: English keywords should match
        result_with_exp, expansion = compute_lexical_score_with_expansion(query, chunk_text, title)
        assert expansion.applied is True
        assert result_with_exp.score > 0.0

    def test_chinese_query_method_matches_method(self):
        """中文'方法'扩展后能匹配英文 method."""
        from app.services.lexical_retrieval import compute_lexical_score, compute_lexical_score_with_expansion

        query = "这篇论文的方法是什么"
        chunk_text = "We propose a novel method for language understanding."

        result_no_exp = compute_lexical_score(query, chunk_text)
        assert result_no_exp.score == 0.0

        result_with_exp, expansion = compute_lexical_score_with_expansion(query, chunk_text)
        assert expansion.applied is True
        assert result_with_exp.score > 0.0

    def test_chinese_query_limitation_matches_limitation(self):
        """中文'局限'扩展后能匹配英文 limitation."""
        from app.services.lexical_retrieval import compute_lexical_score, compute_lexical_score_with_expansion

        query = "这篇论文有什么局限"
        chunk_text = "One limitation of our approach is the computational cost."

        result_no_exp = compute_lexical_score(query, chunk_text)
        assert result_no_exp.score == 0.0

        result_with_exp, expansion = compute_lexical_score_with_expansion(query, chunk_text)
        assert expansion.applied is True
        assert result_with_exp.score > 0.0

    def test_english_query_no_expansion_same_score(self):
        """英文 query 不扩展，分数不变."""
        from app.services.lexical_retrieval import compute_lexical_score, compute_lexical_score_with_expansion

        query = "What is the main contribution?"
        chunk_text = "The main contribution is a novel attention mechanism."

        result_no_exp = compute_lexical_score(query, chunk_text)
        result_with_exp, expansion = compute_lexical_score_with_expansion(query, chunk_text)
        assert expansion.applied is False
        assert result_with_exp.score == result_no_exp.score


# ============================================================
# RAG service integration with query expansion
# ============================================================

class TestRAGServiceQueryExpansion:
    @pytest.mark.asyncio
    @patch("app.services.rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.rag_service.settings")
    async def test_chinese_query_triggers_expansion(self, mock_settings, mock_local):
        """中文问题触发 query expansion."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3
        mock_settings.QUERY_EXPANSION_ENABLED = True
        mock_settings.QUERY_EXPANSION_MODE = "static"

        from app.services.rag_service import RAGService, RetrievedChunk

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed", title="Attention Paper")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        # Simulate expanded query matching English chunk
        chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="The main contribution is a novel attention mechanism.",
                score=0.45, vector_score=0.0, lexical_score=0.5, retrieval_mode="lexical",
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=(chunks, QueryExpansionResult(
            original_query="核心贡献",
            expanded_query="核心贡献 core contribution main contribution",
            expanded_terms=["core", "contribution", "main contribution"],
            applied=True,
            reason="chinese_query_expanded",
        )))
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "The main contribution is attention."

        result = await service.ask(paper_id=1, question="这篇论文的核心贡献是什么")
        assert result.query_expansion_applied is True
        assert len(result.expanded_query_terms) > 0
        assert "core" in result.expanded_query_terms or "contribution" in result.expanded_query_terms

    @pytest.mark.asyncio
    @patch("app.services.rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.rag_service.settings")
    async def test_expansion_disabled_no_expansion(self, mock_settings, mock_local):
        """QUERY_EXPANSION_ENABLED=false 时不扩展."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3
        mock_settings.QUERY_EXPANSION_ENABLED = False
        mock_settings.QUERY_EXPANSION_MODE = "static"

        from app.services.rag_service import RAGService, RetrievedChunk

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed", title="Paper")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="Some text.",
                score=0.0, vector_score=0.0, lexical_score=0.0, retrieval_mode="vector",
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=(chunks, QueryExpansionResult(
            original_query="核心贡献",
            expanded_query="核心贡献",
            applied=False,
            reason="expansion_disabled",
        )))

        result = await service.ask(paper_id=1, question="这篇论文的核心贡献是什么")
        assert result.query_expansion_applied is False

    @pytest.mark.asyncio
    @patch("app.services.rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.rag_service.settings")
    async def test_chinese_query_expansion_improves_strict_rag(self, mock_settings, mock_local):
        """中文问题在关键词命中时从 insufficient_context 改善为 answered."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3
        mock_settings.QUERY_EXPANSION_ENABLED = True
        mock_settings.QUERY_EXPANSION_MODE = "static"

        from app.services.rag_service import RAGService, RetrievedChunk

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_paper.return_value = MagicMock(status="completed", title="Attention Paper")
        mock_repo.get_chunk_count.return_value = 5
        mock_repo.get_embedding_count.return_value = 5

        # With expansion, lexical score > threshold
        chunks = [
            RetrievedChunk(
                chunk_id=1, chunk_index=0, page_start=1, page_end=1,
                text_excerpt="The main contribution is a novel attention mechanism for sequence modeling.",
                score=0.45, vector_score=0.0, lexical_score=0.5, retrieval_mode="lexical",
            ),
        ]

        service = RAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve = AsyncMock(return_value=(chunks, QueryExpansionResult(
            original_query="这篇论文的核心贡献是什么",
            expanded_query="这篇论文的核心贡献是什么 core contribution main contribution",
            expanded_terms=["core", "contribution", "main contribution"],
            applied=True,
            reason="chinese_query_expanded",
        )))
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "The core contribution is attention."

        result = await service.ask(paper_id=1, question="这篇论文的核心贡献是什么")
        assert result.status == "answered"
        assert result.query_expansion_applied is True


# ============================================================
# Multi-paper RAG with query expansion
# ============================================================

class TestMultiPaperQueryExpansion:
    @pytest.mark.asyncio
    @patch("app.services.multi_paper_rag_service.is_local_embedding_provider", return_value=True)
    @patch("app.services.multi_paper_rag_service.settings")
    async def test_multi_paper_chinese_query_expansion(self, mock_settings, mock_local):
        """跨论文中文问题可触发 query expansion."""
        mock_settings.LEXICAL_RETRIEVAL_ENABLED = True
        mock_settings.LEXICAL_SCORE_THRESHOLD = 0.15
        mock_settings.RAG_SCORE_THRESHOLD = 0.1
        mock_settings.RAG_EVIDENCE_THRESHOLD = 0.2
        mock_settings.HYBRID_VECTOR_WEIGHT = 0.7
        mock_settings.HYBRID_LEXICAL_WEIGHT = 0.3
        mock_settings.QUERY_EXPANSION_ENABLED = True
        mock_settings.QUERY_EXPANSION_MODE = "static"

        from app.services.multi_paper_rag_service import MultiPaperRAGService, MultiPaperRetrievedChunk

        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_paper_ids.return_value = [1, 2]
        mock_repo.get_paper.return_value = MagicMock(status="completed")

        chunks = [
            MultiPaperRetrievedChunk(
                paper_id=1, paper_title="DL Paper", chunk_id=1, chunk_index=0,
                page_start=1, page_end=1,
                text_excerpt="The main contribution is a novel method for attention.",
                score=0.45, vector_score=0.0, lexical_score=0.5, retrieval_mode="lexical",
            ),
        ]

        service = MultiPaperRAGService(mock_session, user_id="test_user")
        service.repo = mock_repo
        service.embedding_service = AsyncMock()
        service.embedding_service.embed_query.return_value = [0.1] * 384
        service._retrieve_multi = AsyncMock(return_value=(chunks, QueryExpansionResult(
            original_query="核心贡献",
            expanded_query="核心贡献 core contribution main contribution",
            expanded_terms=["core", "contribution", "main contribution"],
            applied=True,
            reason="chinese_query_expanded",
        )))
        service.llm_provider = AsyncMock()
        service.llm_provider.generate_answer.return_value = "The core contribution is attention."

        result = await service.ask(question="这几篇论文的核心贡献是什么", paper_ids=[1, 2])
        assert result.query_expansion_applied is True
        assert result.status == "answered"
