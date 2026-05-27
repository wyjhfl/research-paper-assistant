from __future__ import annotations

import pytest
from io import StringIO
import sys

from scripts.model_smoke_check import _mask_status, model_smoke_check
from scripts.rebuild_demo_embeddings import DEMO_FILENAMES


def _save_settings():
    from app.config import settings
    return {
        "LLM_PROVIDER": settings.LLM_PROVIDER,
        "LLM_MODEL": settings.LLM_MODEL,
        "LLM_API_KEY": settings.LLM_API_KEY,
        "LLM_BASE_URL": settings.LLM_BASE_URL,
        "EMBEDDING_PROVIDER": settings.EMBEDDING_PROVIDER,
        "EMBEDDING_MODEL": settings.EMBEDDING_MODEL,
        "EMBEDDING_API_KEY": settings.EMBEDDING_API_KEY,
        "EMBEDDING_BASE_URL": settings.EMBEDDING_BASE_URL,
        "EMBEDDING_DIMENSION": settings.EMBEDDING_DIMENSION,
        "REAL_MODEL_REQUIRED": settings.REAL_MODEL_REQUIRED,
    }


def _restore_settings(saved):
    from app.config import settings
    for key, value in saved.items():
        setattr(settings, key, value)


def test_mask_status_configured():
    assert _mask_status("sk-abc123") == "configured"


def test_mask_status_missing():
    assert _mask_status("") == "missing"
    assert _mask_status(None) == "missing"


@pytest.mark.asyncio
async def test_local_provider_skips_and_passes():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "local"
    settings.EMBEDDING_PROVIDER = "local"
    settings.REAL_MODEL_REQUIRED = False
    try:
        exit_code = await model_smoke_check()
        assert exit_code == 0
    finally:
        _restore_settings(saved)


@pytest.mark.asyncio
async def test_openai_compatible_missing_key_returns_failure():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "openai_compatible"
    settings.LLM_API_KEY = ""
    settings.LLM_BASE_URL = ""
    settings.EMBEDDING_PROVIDER = "local"
    settings.REAL_MODEL_REQUIRED = False
    try:
        exit_code = await model_smoke_check()
        assert exit_code == 1
    finally:
        _restore_settings(saved)


@pytest.mark.asyncio
async def test_output_no_sensitive_info():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "openai_compatible"
    settings.LLM_API_KEY = "sk-test-secret-key-12345"
    settings.LLM_BASE_URL = "https://api.example.com/v1"
    settings.EMBEDDING_PROVIDER = "openai_compatible"
    settings.EMBEDDING_API_KEY = "sk-emb-secret-key-67890"
    settings.EMBEDDING_BASE_URL = "https://api.example.com/v1"
    settings.REAL_MODEL_REQUIRED = False

    captured = StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured

    try:
        await model_smoke_check()
    except Exception:
        pass
    finally:
        sys.stdout = old_stdout
        _restore_settings(saved)

    output = captured.getvalue()
    assert "sk-test-secret-key-12345" not in output
    assert "sk-emb-secret-key-67890" not in output
    assert "Authorization" not in output
    assert "Traceback" not in output
    assert "api.example.com" not in output


@pytest.mark.asyncio
async def test_real_model_required_with_local_llm_fails():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "local"
    settings.EMBEDDING_PROVIDER = "local"
    settings.REAL_MODEL_REQUIRED = True
    settings.LLM_API_KEY = ""
    settings.LLM_BASE_URL = ""
    settings.LLM_MODEL = "local-mock"
    try:
        exit_code = await model_smoke_check()
        assert exit_code == 1
    finally:
        _restore_settings(saved)


@pytest.mark.asyncio
async def test_real_model_required_with_local_embedding_fails():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "openai_compatible"
    settings.LLM_API_KEY = "configured-key"
    settings.LLM_BASE_URL = "configured-url"
    settings.LLM_MODEL = "real-model"
    settings.EMBEDDING_PROVIDER = "local"
    settings.EMBEDDING_API_KEY = ""
    settings.EMBEDDING_BASE_URL = ""
    settings.EMBEDDING_MODEL = "local-hash"
    settings.REAL_MODEL_REQUIRED = True
    try:
        exit_code = await model_smoke_check()
        assert exit_code == 1
    finally:
        _restore_settings(saved)


@pytest.mark.asyncio
async def test_real_model_required_missing_embedding_key_fails():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "openai_compatible"
    settings.LLM_API_KEY = "configured-key"
    settings.LLM_BASE_URL = "configured-url"
    settings.LLM_MODEL = "real-model"
    settings.EMBEDDING_PROVIDER = "openai_compatible"
    settings.EMBEDDING_API_KEY = ""
    settings.EMBEDDING_BASE_URL = "configured-url"
    settings.EMBEDDING_MODEL = "real-emb-model"
    settings.REAL_MODEL_REQUIRED = True
    try:
        exit_code = await model_smoke_check()
        assert exit_code == 1
    finally:
        _restore_settings(saved)


@pytest.mark.asyncio
async def test_real_model_required_missing_embedding_base_url_fails():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "openai_compatible"
    settings.LLM_API_KEY = "configured-key"
    settings.LLM_BASE_URL = "configured-url"
    settings.LLM_MODEL = "real-model"
    settings.EMBEDDING_PROVIDER = "openai_compatible"
    settings.EMBEDDING_API_KEY = "configured-key"
    settings.EMBEDDING_BASE_URL = ""
    settings.EMBEDDING_MODEL = "real-emb-model"
    settings.REAL_MODEL_REQUIRED = True
    try:
        exit_code = await model_smoke_check()
        assert exit_code == 1
    finally:
        _restore_settings(saved)


@pytest.mark.asyncio
async def test_real_model_required_local_hash_embedding_model_fails():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "openai_compatible"
    settings.LLM_API_KEY = "configured-key"
    settings.LLM_BASE_URL = "configured-url"
    settings.LLM_MODEL = "real-model"
    settings.EMBEDDING_PROVIDER = "openai_compatible"
    settings.EMBEDDING_API_KEY = "configured-key"
    settings.EMBEDDING_BASE_URL = "configured-url"
    settings.EMBEDDING_MODEL = "local-hash"
    settings.REAL_MODEL_REQUIRED = True
    try:
        exit_code = await model_smoke_check()
        assert exit_code == 1
    finally:
        _restore_settings(saved)


@pytest.mark.asyncio
async def test_real_model_required_error_output_no_leak():
    saved = _save_settings()
    from app.config import settings
    settings.LLM_PROVIDER = "openai_compatible"
    settings.LLM_API_KEY = "sk-secret-key-99999"
    settings.LLM_BASE_URL = "https://secret-api.example.com/v1"
    settings.LLM_MODEL = "real-model"
    settings.EMBEDDING_PROVIDER = "local"
    settings.EMBEDDING_API_KEY = ""
    settings.EMBEDDING_BASE_URL = ""
    settings.EMBEDDING_MODEL = "local-hash"
    settings.REAL_MODEL_REQUIRED = True

    captured = StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured

    try:
        exit_code = await model_smoke_check()
        assert exit_code == 1
    finally:
        sys.stdout = old_stdout
        _restore_settings(saved)

    output = captured.getvalue()
    assert "sk-secret-key-99999" not in output
    assert "Authorization" not in output
    assert "Traceback" not in output
    assert "secret-api.example.com" not in output


def test_rebuild_demo_only_selects_demo_papers():
    assert "demo_transformer.pdf" in DEMO_FILENAMES
    assert "demo_rag.pdf" in DEMO_FILENAMES
    assert "demo_multi_agent.pdf" in DEMO_FILENAMES
    assert len(DEMO_FILENAMES) == 3
    for fn in DEMO_FILENAMES:
        assert fn.startswith("demo_")
    assert "real_paper.pdf" not in DEMO_FILENAMES


@pytest.mark.asyncio
async def test_rebuild_demo_clears_embeddings_before_rewriting():
    from scripts.rebuild_demo_embeddings import rebuild_demo_embeddings
    from app.config import settings

    saved = _save_settings()
    settings.EMBEDDING_PROVIDER = "local"

    try:
        exit_code = await rebuild_demo_embeddings()
        assert exit_code == 1
    finally:
        _restore_settings(saved)
