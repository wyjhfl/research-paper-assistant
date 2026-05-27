from __future__ import annotations

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import PaperChunk
from ..repositories.paper_repo import PaperRepository
from .ai_provider import get_embedding_provider, EmbeddingDimensionError, ProviderRequestError, ProviderResponseError, ProviderConfigurationError
from .model_call_audit_service import record_model_call

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.repo = PaperRepository(session)
        self.provider = get_embedding_provider()

    async def embed_chunks_for_paper(self, paper_id: int) -> int:
        chunks = await self.repo.get_chunks_without_embedding(paper_id)
        if not chunks:
            logger.info("No chunks without embedding for paper_id=%d", paper_id)
            return 0

        texts = [c.text for c in chunks]
        t0 = time.monotonic()
        try:
            embeddings = await self.provider.embed_texts(texts)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await record_model_call(
                user_id=self.user_id,
                operation="embedding_chunks",
                provider=settings.EMBEDDING_PROVIDER,
                model=settings.EMBEDDING_MODEL,
                status="success",
                duration_ms=elapsed_ms,
                input_count=len(texts),
                input_chars=sum(len(t) for t in texts),
                output_chars=0,
                metadata={"paper_id": paper_id, "chunk_count": len(texts)},
            )
        except (EmbeddingDimensionError, ProviderRequestError, ProviderResponseError, ProviderConfigurationError) as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await record_model_call(
                user_id=self.user_id,
                operation="embedding_chunks",
                provider=settings.EMBEDDING_PROVIDER,
                model=settings.EMBEDDING_MODEL,
                status="failed",
                duration_ms=elapsed_ms,
                input_count=len(texts),
                input_chars=sum(len(t) for t in texts),
                output_chars=0,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={"paper_id": paper_id, "chunk_count": len(texts)},
            )
            logger.exception("Embedding provider failed for paper_id=%d", paper_id)
            raise

        if len(embeddings) != len(chunks):
            raise ProviderResponseError(
                f"Embedding count mismatch: got {len(embeddings)} embeddings for {len(chunks)} chunks"
            )

        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        await self.session.flush()
        logger.info(
            "Embedded %d chunks for paper_id=%d", len(chunks), paper_id
        )
        return len(chunks)

    async def embed_query(self, question: str, metadata: dict | None = None) -> list[float]:
        t0 = time.monotonic()
        try:
            results = await self.provider.embed_texts([question])
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            audit_meta = {"query_length": len(question)}
            if metadata:
                audit_meta.update(metadata)
            await record_model_call(
                user_id=self.user_id,
                operation="embedding_query",
                provider=settings.EMBEDDING_PROVIDER,
                model=settings.EMBEDDING_MODEL,
                status="success",
                duration_ms=elapsed_ms,
                input_count=1,
                input_chars=len(question),
                output_chars=0,
                metadata=audit_meta,
            )
            return results[0]
        except (EmbeddingDimensionError, ProviderRequestError, ProviderResponseError, ProviderConfigurationError) as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            audit_meta = {"query_length": len(question)}
            if metadata:
                audit_meta.update(metadata)
            await record_model_call(
                user_id=self.user_id,
                operation="embedding_query",
                provider=settings.EMBEDDING_PROVIDER,
                model=settings.EMBEDDING_MODEL,
                status="failed",
                duration_ms=elapsed_ms,
                input_count=1,
                input_chars=len(question),
                output_chars=0,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata=audit_meta,
            )
            raise
