from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..config import settings
from ..repositories.paper_repo import PaperRepository
from ..models import Paper
from .ai_provider import get_llm_provider, _tokenize, ProviderConfigurationError, ProviderRequestError, ProviderResponseError, EmbeddingDimensionError
from .embedding_service import EmbeddingService
from .lexical_retrieval import (
    compute_lexical_score,
    compute_hybrid_score,
    determine_retrieval_mode,
    is_local_embedding_provider,
)
from .query_expansion import QueryExpansionResult, should_expand_query
from .model_call_audit_service import record_model_call

logger = logging.getLogger(__name__)


def candidate_limit_for_retrieval(base_limit: int) -> int:
    """Return SQL candidate pool size for retrieval before final rerank.

    Local hash embeddings are weak semantic rankers, so lexical reranking needs
    a wider candidate pool. Real embedding providers keep the original limit.
    The returned limit never goes below ``base_limit``.
    """
    safe_base = max(1, int(base_limit))
    if not (is_local_embedding_provider() and settings.LEXICAL_RETRIEVAL_ENABLED):
        return safe_base

    multiplier = max(1, int(settings.RAG_CANDIDATE_MULTIPLIER))
    max_candidates = max(safe_base, int(settings.RAG_MAX_CANDIDATES))
    return max(safe_base, min(safe_base * multiplier, max_candidates))


@dataclass
class RetrievedChunk:
    chunk_id: int
    chunk_index: int
    page_start: int
    page_end: int
    text_excerpt: str
    score: float
    vector_score: float = 0.0
    lexical_score: float = 0.0
    retrieval_mode: str = "vector"


@dataclass
class AnswerResult:
    answer: str
    status: str
    confidence: float
    sources: list[RetrievedChunk]
    evidence_gate_reason: str = ""
    retrieved_source_count: int = 0
    top_source_score: float = 0.0
    query_expansion_applied: bool = False
    expanded_query_terms: list[str] = field(default_factory=list)


class RAGService:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.repo = PaperRepository(session)
        self.embedding_service = EmbeddingService(session, user_id=user_id)
        self.llm_provider = get_llm_provider()

    async def ask(self, paper_id: int, question: str, allow_low_confidence_answer: bool = False) -> AnswerResult:
        paper = await self.repo.get_paper(paper_id, user_id=self.user_id)
        if paper is None:
            raise PaperNotFoundError(paper_id)

        if paper.status != "completed":
            raise PaperNotReadyError(paper_id, paper.status)

        chunks_count = await self.repo.get_chunk_count(paper_id, user_id=self.user_id)
        if chunks_count == 0:
            return AnswerResult(
                answer="该论文暂无文本片段，无法回答问题。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
                evidence_gate_reason="no_chunks",
                retrieved_source_count=0,
                top_source_score=0.0,
            )

        embedding_count = await self.repo.get_embedding_count(paper_id, user_id=self.user_id)
        if embedding_count == 0:
            return AnswerResult(
                answer="该论文的文本片段尚未生成向量索引，无法进行问答。请先重建 embedding。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
                evidence_gate_reason="no_embeddings",
                retrieved_source_count=0,
                top_source_score=0.0,
            )

        query_embedding = await self.embedding_service.embed_query(
            question, metadata={"paper_id": paper_id},
        )

        retrieved, expansion = await self._retrieve(paper_id, query_embedding, question, paper.title)
        exp_applied = expansion.applied
        exp_terms = expansion.expanded_terms[:8] if expansion.applied else []

        if not retrieved:
            return AnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
                evidence_gate_reason="no_retrieved",
                retrieved_source_count=0,
                top_source_score=0.0,
                query_expansion_applied=exp_applied,
                expanded_query_terms=exp_terms,
            )

        top_score = retrieved[0].score
        confidence = min(top_score, 1.0)
        source_count = len(retrieved)

        # Use appropriate score threshold based on retrieval mode
        score_threshold = settings.RAG_SCORE_THRESHOLD
        if is_local_embedding_provider() and settings.LEXICAL_RETRIEVAL_ENABLED:
            score_threshold = settings.LEXICAL_SCORE_THRESHOLD

        if confidence < score_threshold:
            if allow_low_confidence_answer and source_count > 0:
                return await self._generate_low_confidence_answer(
                    question, retrieved, confidence, paper_id, "score_below_threshold",
                    exp_applied, exp_terms,
                )
            return AnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
                evidence_gate_reason="score_below_threshold",
                retrieved_source_count=source_count,
                top_source_score=top_score,
                query_expansion_applied=exp_applied,
                expanded_query_terms=exp_terms,
            )

        # Check query tokens for evidence gate
        from .lexical_retrieval import tokenize as lex_tokenize
        # Use expanded query tokens if expansion was applied
        check_query = expansion.expanded_query if expansion.applied else question
        query_tokens = set(lex_tokenize(check_query))
        if not query_tokens:
            if allow_low_confidence_answer and source_count > 0:
                return await self._generate_low_confidence_answer(
                    question, retrieved, confidence, paper_id, "no_query_tokens",
                    exp_applied, exp_terms,
                )
            return AnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
                evidence_gate_reason="no_query_tokens",
                retrieved_source_count=source_count,
                top_source_score=top_score,
                query_expansion_applied=exp_applied,
                expanded_query_terms=exp_terms,
            )

        # Check lexical evidence overlap
        best_lexical = 0.0
        for r in retrieved:
            if r.lexical_score > best_lexical:
                best_lexical = r.lexical_score

        # Evidence gate: if best lexical overlap is very low even with good hybrid score
        evidence_threshold = settings.RAG_EVIDENCE_THRESHOLD
        if is_local_embedding_provider() and settings.LEXICAL_RETRIEVAL_ENABLED:
            evidence_threshold = settings.LEXICAL_SCORE_THRESHOLD

        if best_lexical < evidence_threshold and not is_local_embedding_provider():
            if allow_low_confidence_answer and source_count > 0:
                return await self._generate_low_confidence_answer(
                    question, retrieved, confidence, paper_id, "evidence_below_threshold",
                    exp_applied, exp_terms,
                )
            return AnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
                evidence_gate_reason="evidence_below_threshold",
                retrieved_source_count=source_count,
                top_source_score=top_score,
                query_expansion_applied=exp_applied,
                expanded_query_terms=exp_terms,
            )

        # For local provider with lexical retrieval: check if any lexical match exists
        if is_local_embedding_provider() and settings.LEXICAL_RETRIEVAL_ENABLED:
            if best_lexical < evidence_threshold:
                if allow_low_confidence_answer and source_count > 0:
                    return await self._generate_low_confidence_answer(
                        question, retrieved, confidence, paper_id, "no_lexical_match",
                        exp_applied, exp_terms,
                    )
                return AnswerResult(
                    answer="当前论文片段不足以回答，不生成无依据答案。",
                    status="insufficient_context",
                    confidence=confidence,
                    sources=retrieved,
                    evidence_gate_reason="no_lexical_match",
                    retrieved_source_count=source_count,
                    top_source_score=top_score,
                    query_expansion_applied=exp_applied,
                    expanded_query_terms=exp_terms,
                )

        contexts = [r.text_excerpt for r in retrieved]
        llm_start = time.monotonic()
        try:
            answer_text = await self.llm_provider.generate_answer(question, contexts)
            await record_model_call(
                user_id=self.user_id,
                operation="llm_answer",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="success",
                duration_ms=int((time.monotonic() - llm_start) * 1000),
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=len(answer_text),
                metadata={"paper_id": paper_id, "context_count": len(contexts)},
            )
        except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError) as e:
            await record_model_call(
                user_id=self.user_id,
                operation="llm_answer",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="failed",
                duration_ms=int((time.monotonic() - llm_start) * 1000),
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=0,
                error_type=type(e).__name__,
                error_message=str(e),
                metadata={"paper_id": paper_id, "context_count": len(contexts)},
            )
            logger.exception("LLM provider failed for paper_id=%d", paper_id)
            return AnswerResult(
                answer=f"AI 服务暂时不可用，无法生成回答。错误类型：{type(e).__name__}",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
                evidence_gate_reason="llm_failed",
                retrieved_source_count=source_count,
                top_source_score=top_score,
                query_expansion_applied=exp_applied,
                expanded_query_terms=exp_terms,
            )

        return AnswerResult(
            answer=answer_text,
            status="answered",
            confidence=confidence,
            sources=retrieved,
            evidence_gate_reason="",
            retrieved_source_count=source_count,
            top_source_score=top_score,
            query_expansion_applied=exp_applied,
            expanded_query_terms=exp_terms,
        )

    async def _generate_low_confidence_answer(
        self,
        question: str,
        retrieved: list[RetrievedChunk],
        confidence: float,
        paper_id: int,
        gate_reason: str,
        query_expansion_applied: bool = False,
        expanded_query_terms: list[str] | None = None,
    ) -> AnswerResult:
        contexts = [r.text_excerpt for r in retrieved]
        source_count = len(retrieved)
        top_score = retrieved[0].score if retrieved else 0.0
        llm_start = time.monotonic()
        try:
            answer_text = await self.llm_provider.generate_answer(question, contexts)
            await record_model_call(
                user_id=self.user_id,
                operation="llm_answer",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="success",
                duration_ms=int((time.monotonic() - llm_start) * 1000),
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=len(answer_text),
                metadata={"paper_id": paper_id, "context_count": len(contexts)},
            )
            return AnswerResult(
                answer="警告：低置信度回答，仅供参考：\n\n" + answer_text,
                status="low_confidence_answer",
                confidence=confidence,
                sources=retrieved,
                evidence_gate_reason=gate_reason,
                retrieved_source_count=source_count,
                top_source_score=top_score,
                query_expansion_applied=query_expansion_applied,
                expanded_query_terms=expanded_query_terms or [],
            )
        except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError) as e:
            await record_model_call(
                user_id=self.user_id,
                operation="llm_answer",
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                status="failed",
                duration_ms=int((time.monotonic() - llm_start) * 1000),
                input_count=len(contexts),
                input_chars=sum(len(c) for c in contexts),
                output_chars=0,
                error_type=type(e).__name__,
                error_message=str(e),
                metadata={"paper_id": paper_id, "context_count": len(contexts)},
            )
            logger.exception("LLM provider failed for low-confidence answer paper_id=%d", paper_id)
            return AnswerResult(
                answer=f"AI 服务暂时不可用，无法生成回答。错误类型：{type(e).__name__}",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
                evidence_gate_reason="llm_failed",
                retrieved_source_count=source_count,
                top_source_score=top_score,
                query_expansion_applied=query_expansion_applied,
                expanded_query_terms=expanded_query_terms or [],
            )

    async def _retrieve(
        self, paper_id: int, query_embedding: list[float], question: str = "", paper_title: str = "",
    ) -> tuple[list[RetrievedChunk], QueryExpansionResult]:
        emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        sql = text("""
            SELECT pc.id, pc.chunk_index, pc.page_start, pc.page_end, pc.text,
                   1 - (pc.embedding <=> :query_vec) AS score
            FROM paper_chunks pc
            JOIN papers p ON p.id = pc.paper_id
            WHERE pc.paper_id = :paper_id
              AND p.user_id = :user_id
              AND pc.embedding IS NOT NULL
            ORDER BY pc.embedding <=> :query_vec
            LIMIT :limit
        """)
        candidate_limit = candidate_limit_for_retrieval(settings.RAG_TOP_K)
        result = await self.session.execute(
            sql,
            {
                "query_vec": emb_str,
                "paper_id": paper_id,
                "user_id": self.user_id,
                "limit": candidate_limit,
            },
        )
        rows = result.fetchall()

        # Compute query expansion once for all chunks
        expansion_result = QueryExpansionResult(
            original_query=question, expanded_query=question, applied=False, reason="",
        )
        if (
            settings.LEXICAL_RETRIEVAL_ENABLED
            and question
            and should_expand_query(settings.QUERY_EXPANSION_ENABLED, settings.QUERY_EXPANSION_MODE)
        ):
            from .query_expansion import expand_query
            expansion_result = expand_query(question)

        scoring_query = expansion_result.expanded_query if expansion_result.applied else question

        retrieved: list[RetrievedChunk] = []
        for row in rows:
            text_val = row.text
            excerpt = text_val[:300] + ("..." if len(text_val) > 300 else "")
            vector_score = max(0.0, min(1.0, row.score))

            # Compute lexical score if enabled
            lexical = 0.0
            final_score = vector_score
            retrieval_mode = "vector"

            if settings.LEXICAL_RETRIEVAL_ENABLED and question:
                lex_result = compute_lexical_score(
                    scoring_query, text_val, paper_title,
                )
                lexical = lex_result.score
                final_score = compute_hybrid_score(
                    vector_score, lexical,
                    settings.HYBRID_VECTOR_WEIGHT, settings.HYBRID_LEXICAL_WEIGHT,
                )
                retrieval_mode = determine_retrieval_mode(vector_score, lexical)

            retrieved.append(
                RetrievedChunk(
                    chunk_id=row.id,
                    chunk_index=row.chunk_index,
                    page_start=row.page_start,
                    page_end=row.page_end,
                    text_excerpt=excerpt,
                    score=round(final_score, 4),
                    vector_score=round(vector_score, 4),
                    lexical_score=round(lexical, 4),
                    retrieval_mode=retrieval_mode,
                )
            )

        # Re-sort by final hybrid score, then keep public response size stable.
        retrieved.sort(key=lambda r: r.score, reverse=True)
        return retrieved[: settings.RAG_TOP_K], expansion_result


class PaperNotFoundError(Exception):
    def __init__(self, paper_id: int):
        self.paper_id = paper_id
        super().__init__(f"Paper {paper_id} not found")


class PaperNotReadyError(Exception):
    def __init__(self, paper_id: int, status: str):
        self.paper_id = paper_id
        self.status = status
        super().__init__(f"Paper {paper_id} is not ready (status={status})")
