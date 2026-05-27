from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.config import settings
from app.database import async_session, init_db
from app.models import Paper


def _mask_status(value: str | None) -> str:
    if not value:
        return "missing"
    return "configured"


async def model_smoke_check():
    results = []

    print("=" * 60)
    print("Model Smoke Check")
    print("=" * 60)

    print("\n--- Provider Config ---")
    print(f"  LLM Provider:       {settings.LLM_PROVIDER}")
    print(f"  LLM Model:          {settings.LLM_MODEL}")
    print(f"  LLM API Key:        {_mask_status(settings.LLM_API_KEY)}")
    print(f"  LLM Base URL:       {_mask_status(settings.LLM_BASE_URL)}")
    print(f"  Embedding Provider: {settings.EMBEDDING_PROVIDER}")
    print(f"  Embedding Model:    {settings.EMBEDDING_MODEL}")
    print(f"  Embedding API Key:  {_mask_status(settings.EMBEDDING_API_KEY)}")
    print(f"  Embedding Base URL: {_mask_status(settings.EMBEDDING_BASE_URL)}")
    print(f"  Embedding Dim:      {settings.EMBEDDING_DIMENSION}")
    print(f"  REAL_MODEL_REQUIRED:{settings.REAL_MODEL_REQUIRED}")

    if settings.REAL_MODEL_REQUIRED:
        print("\n--- REAL_MODEL_REQUIRED Validation ---")
        req_ok = _check_real_model_required()
        if not req_ok:
            print("\n" + "=" * 60)
            print("RESULT: SOME CHECKS FAILED")
            print("=" * 60)
            return 1
        results.append(True)

    llm_is_openai = settings.LLM_PROVIDER == "openai_compatible"
    emb_is_openai = settings.EMBEDDING_PROVIDER == "openai_compatible"

    if not llm_is_openai and not emb_is_openai:
        if settings.REAL_MODEL_REQUIRED:
            print("\n  FAIL: REAL_MODEL_REQUIRED=true but no openai_compatible provider configured")
            print("\n" + "=" * 60)
            print("RESULT: SOME CHECKS FAILED")
            print("=" * 60)
            return 1
        print("\n  SKIP: 当前使用 local provider，无需连通性测试")
        print("\n" + "=" * 60)
        print("RESULT: ALL CHECKS PASSED (local mode)")
        print("=" * 60)
        return 0

    if emb_is_openai:
        print("\n--- Embedding Connectivity ---")
        emb_ok = await _check_embedding()
        results.append(emb_ok)
    else:
        print("\n--- Embedding Connectivity ---")
        print("  SKIP: embedding provider is local")
        results.append(True)

    if llm_is_openai:
        print("\n--- LLM Connectivity ---")
        llm_ok = await _check_llm()
        results.append(llm_ok)
    else:
        print("\n--- LLM Connectivity ---")
        print("  SKIP: LLM provider is local")
        results.append(True)

    if emb_is_openai or llm_is_openai:
        print("\n--- Demo RAG Check ---")
        rag_ok = await _check_rag(emb_is_openai)
        results.append(rag_ok)

    print("\n" + "=" * 60)
    all_pass = all(results)
    if all_pass:
        print("RESULT: ALL CHECKS PASSED")
    else:
        print("RESULT: SOME CHECKS FAILED")
    print("=" * 60)

    return 0 if all_pass else 1


def _check_real_model_required() -> bool:
    if settings.LLM_PROVIDER != "openai_compatible":
        print("  FAIL: REAL_MODEL_REQUIRED=true but LLM_PROVIDER is not openai_compatible")
        return False
    if not settings.LLM_API_KEY:
        print("  FAIL: REAL_MODEL_REQUIRED=true but LLM_API_KEY is missing")
        return False
    if not settings.LLM_BASE_URL:
        print("  FAIL: REAL_MODEL_REQUIRED=true but LLM_BASE_URL is missing")
        return False
    if not settings.LLM_MODEL or settings.LLM_MODEL == "local-mock":
        print("  FAIL: REAL_MODEL_REQUIRED=true but LLM_MODEL is not configured")
        return False
    if settings.EMBEDDING_PROVIDER != "openai_compatible":
        print("  FAIL: REAL_MODEL_REQUIRED=true but EMBEDDING_PROVIDER is not openai_compatible")
        return False
    if not settings.EMBEDDING_API_KEY:
        print("  FAIL: REAL_MODEL_REQUIRED=true but EMBEDDING_API_KEY is missing")
        return False
    if not settings.EMBEDDING_BASE_URL:
        print("  FAIL: REAL_MODEL_REQUIRED=true but EMBEDDING_BASE_URL is missing")
        return False
    if not settings.EMBEDDING_MODEL or settings.EMBEDDING_MODEL == "local-hash":
        print("  FAIL: REAL_MODEL_REQUIRED=true but EMBEDDING_MODEL is not configured")
        return False
    print("  PASS: REAL_MODEL_REQUIRED validation passed")
    return True


async def _check_embedding() -> bool:
    if not settings.EMBEDDING_API_KEY:
        print("  FAIL: EMBEDDING_API_KEY is required for openai_compatible")
        return False
    if not settings.EMBEDDING_BASE_URL:
        print("  FAIL: EMBEDDING_BASE_URL is required for openai_compatible")
        return False

    try:
        from app.services.ai_provider import get_embedding_provider

        provider = get_embedding_provider()
        text = "Transformer attention improves parallel sequence modeling."
        embeddings = await provider.embed_texts([text])

        if not embeddings or len(embeddings) == 0:
            print("  FAIL: embedding returned empty result")
            return False

        vec = embeddings[0]
        actual_dim = len(vec)
        if actual_dim != settings.EMBEDDING_DIMENSION:
            print(f"  FAIL: dimension mismatch (expected {settings.EMBEDDING_DIMENSION}, got {actual_dim})")
            print(f"  ACTION: update EMBEDDING_DIMENSION={actual_dim} and rebuild DB volume or migrate")
            return False

        print(f"  PASS: embedding returned vector of dimension {actual_dim}")
        return True

    except Exception:
        print("  FAIL: internal_error: embedding check failed")
        print("  NOTE: the model may not support embedding endpoint, consider using a dedicated embedding model")
        return False


async def _check_llm() -> bool:
    if not settings.LLM_API_KEY:
        print("  FAIL: LLM_API_KEY is required for openai_compatible")
        return False
    if not settings.LLM_BASE_URL:
        print("  FAIL: LLM_BASE_URL is required for openai_compatible")
        return False

    try:
        from app.services.ai_provider import get_llm_provider

        provider = get_llm_provider()
        question = "What is attention used for in Transformer models?"
        contexts = [
            "Attention allows Transformer models to relate tokens in a sequence "
            "and compute contextual representations in parallel."
        ]
        answer = await provider.generate_answer(question, contexts)

        if not answer or not answer.strip():
            print("  FAIL: LLM returned empty answer")
            return False

        preview = answer.strip()[:200]
        print(f"  PASS: LLM returned answer")
        print(f"  Preview: {preview}")
        return True

    except Exception:
        print("  FAIL: internal_error: LLM check failed")
        return False


async def _check_rag(emb_is_openai: bool) -> bool:
    try:
        await init_db()

        async with async_session() as session:
            result = await session.execute(
                select(Paper).where(Paper.filename == "demo_transformer.pdf")
            )
            demo_paper = result.scalar_one_or_none()

            if demo_paper is None:
                print("  SKIP: demo data not found, run seed_demo.py first")
                return True

            if emb_is_openai:
                from sqlalchemy import func, text as sql_text

                chunk_result = await session.execute(
                    sql_text(
                        "SELECT COUNT(*) FROM paper_chunks "
                        "WHERE paper_id = :pid AND embedding IS NOT NULL"
                    ).bindparams(pid=demo_paper.id)
                )
                chunk_count = chunk_result.scalar()
                if chunk_count == 0:
                    print("  WARN: demo paper has no embeddings, run rebuild_demo_embeddings.py first")
                    print("  NOTE: if demo was seeded with local provider, embeddings must be rebuilt with real provider")
                    return True

            from app.services.rag_service import RAGService

            rag = RAGService(session)
            answer_result = await rag.ask(
                demo_paper.id, "What problem does attention solve?"
            )

            if answer_result.status not in ("answered", "insufficient_context"):
                print(f"  FAIL: unexpected status={answer_result.status}")
                return False

            if answer_result.status == "answered" and len(answer_result.sources) < 1:
                print("  FAIL: answered but no sources")
                return False

            print(f"  PASS: RAG status={answer_result.status}, sources={len(answer_result.sources)}")
            return True

    except Exception:
        print("  FAIL: internal_error: RAG check failed")
        return False


if __name__ == "__main__":
    sys.exit(asyncio.run(model_smoke_check()))
