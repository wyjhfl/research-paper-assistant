from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, bindparam

from ..config import settings
from ..models import Paper, PaperChunk
from ..repositories.paper_repo import PaperRepository
from .ai_provider import get_llm_provider, _tokenize, ProviderConfigurationError, ProviderRequestError, ProviderResponseError
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


@dataclass
class MultiPaperRetrievedChunk:
    paper_id: int
    paper_title: str
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
class MultiPaperAnswerResult:
    answer: str
    status: str
    confidence: float
    sources: list[MultiPaperRetrievedChunk]
    evidence_gate_reason: str = ""
    retrieved_source_count: int = 0
    top_source_score: float = 0.0
    query_expansion_applied: bool = False
    expanded_query_terms: list[str] = field(default_factory=list)


class MultiPaperRAGService:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.repo = PaperRepository(session)
        self.embedding_service = EmbeddingService(session, user_id=user_id)
        self.llm_provider = get_llm_provider()

    async def _get_eligible_paper_ids(
        self, paper_ids: list[int] | None = None
    ) -> list[int]:
        if paper_ids:
            valid_ids: list[int] = []
            for pid in paper_ids:
                paper = await self.repo.get_paper(pid, user_id=self.user_id)
                if paper is not None and paper.status == "completed":
                    valid_ids.append(pid)
            return valid_ids

        return await self.repo.get_completed_paper_ids(user_id=self.user_id)

    async def _retrieve_multi(
        self,
        query_embedding: list[float],
        paper_ids: list[int],
        top_k: int = 8,
        per_paper_limit: int = 3,
        question: str = "",
    ) -> tuple[list[MultiPaperRetrievedChunk], QueryExpansionResult]:
        if not paper_ids:
            return [], QueryExpansionResult(original_query=question, expanded_query=question, applied=False, reason="no_papers")

        emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        candidate_limit = top_k * len(paper_ids)

        sql = text("""
            SELECT pc.id, pc.chunk_index, pc.page_start, pc.page_end, pc.text,
                   pc.paper_id, p.title AS paper_title,
                   1 - (pc.embedding <=> :query_vec) AS score
            FROM paper_chunks pc
            JOIN papers p ON p.id = pc.paper_id
            WHERE pc.paper_id IN :pids
              AND pc.embedding IS NOT NULL
            ORDER BY pc.embedding <=> :query_vec
            LIMIT :candidate_limit
        """).bindparams(
            bindparam("pids", expanding=True),
        )

        result = await self.session.execute(
            sql,
            {
                "query_vec": emb_str,
                "pids": tuple(paper_ids),
                "candidate_limit": candidate_limit,
            },
        )
        rows = result.fetchall()

        # Build paper_id -> title map for lexical scoring
        paper_titles: dict[int, str] = {}
        for row in rows:
            if row.paper_id not in paper_titles:
                paper_titles[row.paper_id] = row.paper_title

        per_paper_count: dict[int, int] = {}
        candidates: list[MultiPaperRetrievedChunk] = []

        expansion_result = QueryExpansionResult(original_query=question, expanded_query=question, applied=False, reason="")
        if (
            settings.LEXICAL_RETRIEVAL_ENABLED
            and question
            and should_expand_query(settings.QUERY_EXPANSION_ENABLED, settings.QUERY_EXPANSION_MODE)
        ):
            from .query_expansion import expand_query
            expansion_result = expand_query(question)

        scoring_query = expansion_result.expanded_query if expansion_result.applied else question

        for row in rows:
            pid = row.paper_id
            text_val = row.text
            excerpt = text_val[:300] + ("..." if len(text_val) > 300 else "")
            vector_score = max(0.0, min(1.0, row.score))

            # Compute lexical score if enabled
            lexical = 0.0
            final_score = vector_score
            retrieval_mode = "vector"

            if settings.LEXICAL_RETRIEVAL_ENABLED and question:
                lex_result = compute_lexical_score(
                    scoring_query, text_val, row.paper_title,
                )
                lexical = lex_result.score
                final_score = compute_hybrid_score(
                    vector_score, lexical,
                    settings.HYBRID_VECTOR_WEIGHT, settings.HYBRID_LEXICAL_WEIGHT,
                )
                retrieval_mode = determine_retrieval_mode(vector_score, lexical)

            candidates.append(
                MultiPaperRetrievedChunk(
                    paper_id=pid,
                    paper_title=row.paper_title,
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

        # Sort by hybrid score, then apply per-paper limit
        candidates.sort(key=lambda r: r.score, reverse=True)

        retrieved: list[MultiPaperRetrievedChunk] = []
        for c in candidates:
            pid = c.paper_id
            if per_paper_count.get(pid, 0) >= per_paper_limit:
                continue
            retrieved.append(c)
            per_paper_count[pid] = per_paper_count.get(pid, 0) + 1
            if len(retrieved) >= top_k:
                break

        return retrieved, expansion_result

    async def search(
        self,
        query: str,
        paper_ids: list[int] | None = None,
        top_k: int = 10,
    ) -> list[MultiPaperRetrievedChunk]:
        top_k = max(1, min(top_k, 50))
        eligible_ids = await self._get_eligible_paper_ids(paper_ids)
        if not eligible_ids:
            return []

        query_embedding = await self.embedding_service.embed_query(
            query, metadata={"paper_ids": eligible_ids},
        )
        per_paper_limit = max(top_k // 2, 2)
        retrieved, _ = await self._retrieve_multi(
            query_embedding, eligible_ids, top_k=top_k, per_paper_limit=per_paper_limit,
            question=query,
        )
        return retrieved

    async def ask(
        self,
        question: str,
        paper_ids: list[int] | None = None,
        top_k: int = 8,
        allow_low_confidence_answer: bool = False,
    ) -> MultiPaperAnswerResult:
        top_k = max(1, min(top_k, 20))
        eligible_ids = await self._get_eligible_paper_ids(paper_ids)
        if not eligible_ids:
            return MultiPaperAnswerResult(
                answer="没有可用的已完成论文，无法进行问答。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
                evidence_gate_reason="no_chunks",
                retrieved_source_count=0,
                top_source_score=0.0,
                query_expansion_applied=False,
                expanded_query_terms=[],
            )

        query_embedding = await self.embedding_service.embed_query(
            question, metadata={"paper_ids": eligible_ids},
        )

        per_paper_limit = max(top_k // 2, 2)
        retrieved, expansion = await self._retrieve_multi(
            query_embedding, eligible_ids, top_k=top_k, per_paper_limit=per_paper_limit,
            question=question,
        )

        exp_applied = expansion.applied
        exp_terms = expansion.expanded_terms[:8] if expansion.applied else []

        if not retrieved:
            return MultiPaperAnswerResult(
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
                    question, retrieved, confidence, eligible_ids, "score_below_threshold",
                    query_expansion_applied=exp_applied,
                    expanded_query_terms=exp_terms,
                )
            return MultiPaperAnswerResult(
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
        check_query = expansion.expanded_query if expansion.applied else question
        query_tokens = set(lex_tokenize(check_query))
        if not query_tokens:
            if allow_low_confidence_answer and source_count > 0:
                return await self._generate_low_confidence_answer(
                    question, retrieved, confidence, eligible_ids, "no_query_tokens",
                    query_expansion_applied=exp_applied,
                    expanded_query_terms=exp_terms,
                )
            return MultiPaperAnswerResult(
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

        evidence_threshold = settings.RAG_EVIDENCE_THRESHOLD
        if is_local_embedding_provider() and settings.LEXICAL_RETRIEVAL_ENABLED:
            evidence_threshold = settings.LEXICAL_SCORE_THRESHOLD

        if best_lexical < evidence_threshold and not is_local_embedding_provider():
            if allow_low_confidence_answer and source_count > 0:
                return await self._generate_low_confidence_answer(
                    question, retrieved, confidence, eligible_ids, "evidence_below_threshold",
                    query_expansion_applied=exp_applied,
                    expanded_query_terms=exp_terms,
                )
            return MultiPaperAnswerResult(
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
                        question, retrieved, confidence, eligible_ids, "no_lexical_match",
                        query_expansion_applied=exp_applied,
                        expanded_query_terms=exp_terms,
                    )
                return MultiPaperAnswerResult(
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
                metadata={"paper_ids": eligible_ids, "context_count": len(contexts)},
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
                metadata={"paper_ids": eligible_ids, "context_count": len(contexts)},
            )
            logger.exception("LLM provider failed in multi-paper ask")
            return MultiPaperAnswerResult(
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

        return MultiPaperAnswerResult(
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
        retrieved: list[MultiPaperRetrievedChunk],
        confidence: float,
        eligible_ids: list[int],
        gate_reason: str,
        query_expansion_applied: bool = False,
        expanded_query_terms: list[str] | None = None,
    ) -> MultiPaperAnswerResult:
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
                metadata={"paper_ids": eligible_ids, "context_count": len(contexts)},
            )
            return MultiPaperAnswerResult(
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
                metadata={"paper_ids": eligible_ids, "context_count": len(contexts)},
            )
            logger.exception("LLM provider failed in multi-paper low-confidence ask")
            return MultiPaperAnswerResult(
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
