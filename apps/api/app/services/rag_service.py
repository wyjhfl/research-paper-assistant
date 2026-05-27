from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..config import settings
from ..repositories.paper_repo import PaperRepository
from ..models import Paper
from .ai_provider import get_llm_provider, _tokenize, ProviderConfigurationError, ProviderRequestError, ProviderResponseError, EmbeddingDimensionError
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


@dataclass
class RetrievedChunk:
    chunk_id: int
    chunk_index: int
    page_start: int
    page_end: int
    text_excerpt: str
    score: float


@dataclass
class AnswerResult:
    answer: str
    status: str
    confidence: float
    sources: list[RetrievedChunk]


def _lexical_overlap(query_tokens: set[str], source_tokens: set[str]) -> float:
    if not query_tokens or not source_tokens:
        return 0.0
    overlap = query_tokens & source_tokens
    return len(overlap) / len(query_tokens)


class RAGService:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.repo = PaperRepository(session)
        self.embedding_service = EmbeddingService(session, user_id=user_id)
        self.llm_provider = get_llm_provider()

    async def ask(self, paper_id: int, question: str) -> AnswerResult:
        paper = await self.repo.get_paper(paper_id, user_id=self.user_id)
        if paper is None:
            raise PaperNotFoundError(paper_id)

        if paper.status != "completed":
            raise PaperNotReadyError(paper_id, paper.status)

        chunks_count = await self.repo.get_chunk_count(paper_id)
        if chunks_count == 0:
            return AnswerResult(
                answer="该论文暂无文本片段，无法回答问题。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
            )

        embedding_count = await self.repo.get_embedding_count(paper_id)
        if embedding_count == 0:
            return AnswerResult(
                answer="该论文的文本片段尚未生成向量索引，无法进行问答。请先重建 embedding。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
            )

        query_embedding = await self.embedding_service.embed_query(
            question, metadata={"paper_id": paper_id},
        )

        retrieved = await self._retrieve(paper_id, query_embedding)

        if not retrieved:
            return AnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=0.0,
                sources=[],
            )

        top_score = retrieved[0].score
        confidence = min(top_score, 1.0)

        if confidence < settings.RAG_SCORE_THRESHOLD:
            return AnswerResult(
                answer="当前论文片段不足以回答，不生成无依据答案。",
                status="insufficient_context",
                confidence=confidence,
                sources=retrieved,
            )

        query_tokens = _remove_stop_words(set(_tokenize(question)))
        if not query_tokens:
            return AnswerResult(
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
            return AnswerResult(
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
            )

        return AnswerResult(
            answer=answer_text,
            status="answered",
            confidence=confidence,
            sources=retrieved,
        )

    async def _retrieve(
        self, paper_id: int, query_embedding: list[float]
    ) -> list[RetrievedChunk]:
        emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        sql = text("""
            SELECT id, chunk_index, page_start, page_end, text,
                   1 - (embedding <=> :query_vec) AS score
            FROM paper_chunks
            WHERE paper_id = :paper_id AND embedding IS NOT NULL
            ORDER BY embedding <=> :query_vec
            LIMIT :limit
        """)
        result = await self.session.execute(
            sql,
            {
                "query_vec": emb_str,
                "paper_id": paper_id,
                "limit": settings.RAG_TOP_K,
            },
        )
        rows = result.fetchall()

        retrieved: list[RetrievedChunk] = []
        for row in rows:
            text_val = row.text
            excerpt = text_val[:300] + ("..." if len(text_val) > 300 else "")
            score = max(0.0, min(1.0, row.score))
            retrieved.append(
                RetrievedChunk(
                    chunk_id=row.id,
                    chunk_index=row.chunk_index,
                    page_start=row.page_start,
                    page_end=row.page_end,
                    text_excerpt=excerpt,
                    score=round(score, 4),
                )
            )
        return retrieved


class PaperNotFoundError(Exception):
    def __init__(self, paper_id: int):
        self.paper_id = paper_id
        super().__init__(f"Paper {paper_id} not found")


class PaperNotReadyError(Exception):
    def __init__(self, paper_id: int, status: str):
        self.paper_id = paper_id
        self.status = status
        super().__init__(f"Paper {paper_id} is not ready (status={status})")
