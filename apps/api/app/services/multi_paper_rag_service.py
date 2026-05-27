from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, bindparam

from ..config import settings
from ..models import Paper, PaperChunk
from ..repositories.paper_repo import PaperRepository
from .ai_provider import get_llm_provider, _tokenize, ProviderConfigurationError, ProviderRequestError, ProviderResponseError
from .embedding_service import EmbeddingService
from .model_call_audit_service import record_model_call

logger = logging.getLogger(__name__)

_STOP_WORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "of", "in", "to",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out", "off",
    "over", "under", "again", "further", "then", "once", "and", "but", "or",
    "nor", "not", "so", "yet", "both", "either", "neither", "each", "every",
    "all", "any", "few", "more", "most", "other", "some", "such", "no",
    "only", "own", "same", "than", "too", "very", "just", "because",
    "if", "when", "where", "how", "what", "which", "who", "whom", "this",
    "that", "these", "those", "it", "its", "he", "she", "they", "them",
    "we", "you", "i", "me", "my", "your", "his", "her", "our", "their",
}


def _remove_stop_words(tokens: set[str]) -> set[str]:
    return tokens - _STOP_WORDS


def _lexical_overlap(query_tokens: set[str], source_tokens: set[str]) -> float:
    if not query_tokens or not source_tokens:
        return 0.0
    overlap = query_tokens & source_tokens
    return len(overlap) / len(query_tokens)


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


@dataclass
class MultiPaperAnswerResult:
    answer: str
    status: str
    confidence: float
    sources: list[MultiPaperRetrievedChunk]


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
    ) -> list[MultiPaperRetrievedChunk]:
        if not paper_ids:
            return []

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

        per_paper_count: dict[int, int] = {}
        retrieved: list[MultiPaperRetrievedChunk] = []

        for row in rows:
            pid = row.paper_id
            if per_paper_count.get(pid, 0) >= per_paper_limit:
                continue

            text_val = row.text
            excerpt = text_val[:300] + ("..." if len(text_val) > 300 else "")
            score = max(0.0, min(1.0, row.score))

            retrieved.append(
                MultiPaperRetrievedChunk(
                    paper_id=pid,
                    paper_title=row.paper_title,
                    chunk_id=row.id,
                    chunk_index=row.chunk_index,
                    page_start=row.page_start,
                    page_end=row.page_end,
                    text_excerpt=excerpt,
                    score=round(score, 4),
                )
            )
            per_paper_count[pid] = per_paper_count.get(pid, 0) + 1

            if len(retrieved) >= top_k:
                break

        return retrieved

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
        return await self._retrieve_multi(
            query_embedding, eligible_ids, top_k=top_k, per_paper_limit=per_paper_limit
        )

    async def ask(
        self,
        question: str,
        paper_ids: list[int] | None = None,
        top_k: int = 8,
    ) -> MultiPaperAnswerResult:
        top_k = max(1, min(top_k, 20))
        eligible_ids = await self._get_eligible_paper_ids(paper_ids)
        if not eligible_ids:
            return MultiPaperAnswerResult(
                answer="没有可用的已完成论文，无法进行问答。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
            )

        query_embedding = await self.embedding_service.embed_query(
            question, metadata={"paper_ids": eligible_ids},
        )

        per_paper_limit = max(top_k // 2, 2)
        retrieved = await self._retrieve_multi(
            query_embedding, eligible_ids, top_k=top_k, per_paper_limit=per_paper_limit
        )

        if not retrieved:
            return MultiPaperAnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
            )

        top_score = retrieved[0].score
        confidence = min(top_score, 1.0)

        if confidence < settings.RAG_SCORE_THRESHOLD:
            return MultiPaperAnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
            )

        query_tokens = _remove_stop_words(set(_tokenize(question)))
        if not query_tokens:
            return MultiPaperAnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
            )

        best_overlap = 0.0
        for r in retrieved:
            source_tokens = _remove_stop_words(set(_tokenize(r.text_excerpt)))
            overlap = _lexical_overlap(query_tokens, source_tokens)
            if overlap > best_overlap:
                best_overlap = overlap

        if best_overlap < settings.RAG_EVIDENCE_THRESHOLD:
            return MultiPaperAnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
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
            )

        return MultiPaperAnswerResult(
            answer=answer_text,
            status="answered",
            confidence=confidence,
            sources=retrieved,
        )
