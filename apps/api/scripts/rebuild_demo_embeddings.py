from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update

from app.config import settings
from app.database import async_session, init_db
from app.models import Paper, PaperChunk

DEMO_FILENAMES = [
    "demo_transformer.pdf",
    "demo_rag.pdf",
    "demo_multi_agent.pdf",
]


async def rebuild_demo_embeddings():
    print("=" * 60)
    print("Rebuild Demo Embeddings")
    print("=" * 60)

    print(f"\n  Embedding Provider: {settings.EMBEDDING_PROVIDER}")
    print(f"  Embedding Model:    {settings.EMBEDDING_MODEL}")
    print(f"  Embedding Dim:      {settings.EMBEDDING_DIMENSION}")

    if settings.EMBEDDING_PROVIDER == "local":
        print("\n  FAIL: EMBEDDING_PROVIDER is local, cannot rebuild with real embeddings")
        print("  Set EMBEDDING_PROVIDER=openai_compatible to use real embeddings")
        return 1

    try:
        from app.services.ai_provider import get_embedding_provider

        provider = get_embedding_provider()
    except Exception:
        print("\n  FAIL: internal_error: cannot create embedding provider")
        return 1

    await init_db()

    total_rebuilt = 0

    async with async_session() as session:
        for filename in DEMO_FILENAMES:
            result = await session.execute(
                select(Paper).where(Paper.filename == filename)
            )
            paper = result.scalar_one_or_none()

            if paper is None:
                print(f"\n  SKIP: {filename} not found, run seed_demo.py first")
                continue

            try:
                await session.execute(
                    update(PaperChunk)
                    .where(PaperChunk.paper_id == paper.id)
                    .values(embedding=None)
                )
                await session.flush()

                from app.services.embedding_service import EmbeddingService

                emb_service = EmbeddingService(session, user_id="default")
                count = await emb_service.embed_chunks_for_paper(paper.id)
                print(f"\n  REBUILT: {filename} — {count} chunks embedded")
                total_rebuilt += count
            except Exception:
                print(f"\n  FAIL: internal_error: rebuild failed for {filename}")
                return 1

        await session.commit()

    print("\n" + "=" * 60)
    print(f"Total chunks rebuilt: {total_rebuilt}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(rebuild_demo_embeddings()))
