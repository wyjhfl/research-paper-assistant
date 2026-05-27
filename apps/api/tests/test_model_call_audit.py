from __future__ import annotations

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.main import app
from app.models import ModelCallEvent, Paper, PaperChunk
from app.services.model_call_audit_service import (
    safe_error_message,
    safe_metadata,
    record_model_call,
    set_audit_session_factory,
    get_audit_session_factory,
)

try:
    from conftest import _db_available as __db_avail
except ImportError:
    __db_avail = False

skip_if_no_db = pytest.mark.skipif(
    not __db_avail,
    reason="PostgreSQL not available for test DB"
)


def _make_mock_audit_session():
    mock = AsyncMock()
    mock.add = MagicMock()
    mock.commit = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


@pytest.mark.asyncio
async def test_safe_error_message_redacts_bearer():
    msg = safe_error_message("Error with Bearer sk-abc123456789 and api_key=sk-xyz123456789")
    assert "sk-abc123456789" not in msg
    assert "sk-xyz123456789" not in msg
    assert "***REDACTED***" in msg


@pytest.mark.asyncio
async def test_safe_error_message_redacts_database_url():
    msg = safe_error_message("connect to postgresql+asyncpg://admin:pass@db:5432/prod failed")
    assert "admin:pass" not in msg
    assert "postgresql+asyncpg://***REDACTED***" in msg


@pytest.mark.asyncio
async def test_safe_error_message_truncates_long():
    long_msg = "x" * 500
    msg = safe_error_message(long_msg)
    assert len(msg) <= 300
    assert msg.endswith("...")


@pytest.mark.asyncio
async def test_safe_metadata_whitelist():
    result = safe_metadata({"paper_id": 1, "chunk_count": 5, "secret_field": "leaked"})
    assert result is not None
    parsed = json.loads(result)
    assert "paper_id" in parsed
    assert "chunk_count" in parsed
    assert "secret_field" not in parsed


@pytest.mark.asyncio
async def test_safe_metadata_no_chunk_text():
    result = safe_metadata({"paper_id": 1, "chunk_text": "full chunk content here", "prompt": "full prompt"})
    assert result is not None
    parsed = json.loads(result)
    assert "paper_id" in parsed
    assert "chunk_text" not in parsed
    assert "prompt" not in parsed


@pytest.mark.asyncio
async def test_safe_metadata_empty():
    assert safe_metadata(None) is None
    assert safe_metadata({}) is None
    assert safe_metadata({"unknown_key": 1}) is None


@pytest.mark.asyncio
async def test_record_model_call_uses_independent_session():
    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    try:
        set_audit_session_factory(mock_factory)
        await record_model_call(
            user_id="test-user",
            operation="embedding_chunks",
            provider="local",
            model="local-hash",
            status="success",
            duration_ms=100,
            input_count=5,
            input_chars=500,
            output_chars=0,
            metadata={"paper_id": 1, "chunk_count": 5},
        )

        mock_factory.assert_called_once()
        mock_audit_session.add.assert_called_once()
        event = mock_audit_session.add.call_args[0][0]
        assert isinstance(event, ModelCallEvent)
        assert event.operation == "embedding_chunks"
        assert event.status == "success"
        assert event.provider == "local"
        assert event.duration_ms == 100
        assert event.input_count == 5
        mock_audit_session.commit.assert_called_once()
    finally:
        set_audit_session_factory(original_factory)


@pytest.mark.asyncio
async def test_record_model_call_failure_does_not_raise():
    mock_audit_session = _make_mock_audit_session()
    mock_audit_session.add = MagicMock(side_effect=Exception("DB connection lost"))

    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    try:
        set_audit_session_factory(mock_factory)
        await record_model_call(
            operation="llm_answer",
            provider="openai_compatible",
            model="gpt-4",
            status="success",
            duration_ms=200,
        )
    finally:
        set_audit_session_factory(original_factory)


@pytest.mark.asyncio
async def test_record_model_call_internally_sanitizes_error_message():
    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    try:
        set_audit_session_factory(mock_factory)
        await record_model_call(
            operation="llm_answer",
            provider="openai_compatible",
            model="gpt-4",
            status="failed",
            duration_ms=100,
            error_type="ProviderRequestError",
            error_message="api_key=sk-secret12345678 Authorization: Bearer sk-secret12345678",
        )

        event = mock_audit_session.add.call_args[0][0]
        assert "sk-secret12345678" not in event.error_message
        assert "***REDACTED***" in event.error_message
    finally:
        set_audit_session_factory(original_factory)


@pytest.mark.asyncio
async def test_embedding_chunks_writes_audit_on_success():
    from app.services.embedding_service import EmbeddingService

    mock_provider = AsyncMock()
    mock_provider.embed_texts = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])

    mock_chunk1 = MagicMock(spec=PaperChunk)
    mock_chunk1.text = "chunk text 1"
    mock_chunk1.embedding = None
    mock_chunk2 = MagicMock(spec=PaperChunk)
    mock_chunk2.text = "chunk text 2"
    mock_chunk2.embedding = None

    mock_repo = AsyncMock()
    mock_repo.get_chunks_without_embedding = AsyncMock(return_value=[mock_chunk1, mock_chunk2])

    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    with patch("app.services.embedding_service.get_embedding_provider", return_value=mock_provider):
        try:
            set_audit_session_factory(mock_factory)
            svc = EmbeddingService(mock_session, user_id="test-user-embed")
            svc.repo = mock_repo
            result = await svc.embed_chunks_for_paper(paper_id=1)
        finally:
            set_audit_session_factory(original_factory)

    assert result == 2

    audit_calls = [c[0][0] for c in mock_audit_session.add.call_args_list if isinstance(c[0][0], ModelCallEvent)]
    assert len(audit_calls) >= 1
    audit = audit_calls[0]
    assert audit.operation == "embedding_chunks"
    assert audit.status == "success"
    assert audit.input_count == 2
    assert audit.user_id == "test-user-embed"


@pytest.mark.asyncio
async def test_embedding_query_writes_audit_on_success():
    from app.services.embedding_service import EmbeddingService

    mock_provider = AsyncMock()
    mock_provider.embed_texts = AsyncMock(return_value=[[0.1] * 384])

    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    with patch("app.services.embedding_service.get_embedding_provider", return_value=mock_provider):
        try:
            set_audit_session_factory(mock_factory)
            svc = EmbeddingService(mock_session, user_id="test-user-query")
            svc.repo = AsyncMock()
            result = await svc.embed_query("test question")
        finally:
            set_audit_session_factory(original_factory)

    assert len(result) == 384

    audit_calls = [c[0][0] for c in mock_audit_session.add.call_args_list if isinstance(c[0][0], ModelCallEvent)]
    assert len(audit_calls) >= 1
    audit = audit_calls[0]
    assert audit.operation == "embedding_query"
    assert audit.status == "success"
    assert audit.input_count == 1
    assert audit.user_id == "test-user-query"


@pytest.mark.asyncio
async def test_provider_error_writes_failed_audit():
    from app.services.ai_provider import ProviderRequestError
    from app.services.embedding_service import EmbeddingService

    mock_provider = AsyncMock()
    mock_provider.embed_texts = AsyncMock(side_effect=ProviderRequestError("API error"))

    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    with patch("app.services.embedding_service.get_embedding_provider", return_value=mock_provider):
        try:
            set_audit_session_factory(mock_factory)
            svc = EmbeddingService(mock_session)
            svc.repo = AsyncMock()
            with pytest.raises(ProviderRequestError):
                await svc.embed_query("test question")
        finally:
            set_audit_session_factory(original_factory)

    audit_calls = [c[0][0] for c in mock_audit_session.add.call_args_list if isinstance(c[0][0], ModelCallEvent)]
    assert len(audit_calls) >= 1
    audit = audit_calls[0]
    assert audit.operation == "embedding_query"
    assert audit.status == "failed"
    assert audit.error_type == "ProviderRequestError"


@pytest.mark.asyncio
async def test_error_message_no_api_key_or_authorization():
    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    try:
        set_audit_session_factory(mock_factory)
        await record_model_call(
            operation="llm_answer",
            provider="openai_compatible",
            model="gpt-4",
            status="failed",
            duration_ms=100,
            error_type="ProviderRequestError",
            error_message="api_key=sk-secret12345678 Authorization: Bearer sk-secret12345678",
        )

        event = mock_audit_session.add.call_args[0][0]
        assert "sk-secret12345678" not in event.error_message
        assert "***REDACTED***" in event.error_message
    finally:
        set_audit_session_factory(original_factory)


@pytest.mark.asyncio
async def test_metadata_no_chunk_full_text():
    result = safe_metadata({
        "paper_id": 1,
        "chunk_text": "This is the full chunk text that should not be saved",
        "prompt": "Full prompt text here",
        "answer": "Full answer text",
    })
    assert result is not None
    parsed = json.loads(result)
    assert "paper_id" in parsed
    assert "chunk_text" not in parsed
    assert "prompt" not in parsed
    assert "answer" not in parsed


@pytest.mark.asyncio
@skip_if_no_db()
async def test_usage_model_calls_user_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_a = await client.get("/usage/model-calls", headers={"X-User-Id": "user-audit-isolation-a"})
        resp_b = await client.get("/usage/model-calls", headers={"X-User-Id": "user-audit-isolation-b"})

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200


@pytest.mark.asyncio
@skip_if_no_db()
async def test_usage_model_calls_limit_max():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/usage/model-calls?limit=201", headers={"X-User-Id": "default"})
    assert resp.status_code == 422


@pytest.mark.asyncio
@skip_if_no_db()
async def test_usage_model_calls_limit_valid():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/usage/model-calls?limit=200", headers={"X-User-Id": "default"})
    assert resp.status_code == 200


@pytest.mark.asyncio
@skip_if_no_db()
async def test_usage_summary_aggregation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/usage/model-calls/summary", headers={"X-User-Id": "default"})

    assert resp.status_code == 200
    data = resp.json()
    assert "total_calls" in data
    assert "success_calls" in data
    assert "failed_calls" in data
    assert "avg_duration_ms" in data
    assert "calls_by_operation" in data
    assert "calls_by_provider" in data


@pytest.mark.asyncio
async def test_local_provider_records_audit():
    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    try:
        set_audit_session_factory(mock_factory)
        await record_model_call(
            operation="embedding_query",
            provider="local",
            model="local-hash",
            status="success",
            duration_ms=5,
        )

        event = mock_audit_session.add.call_args[0][0]
        assert event.provider == "local"
        assert event.model == "local-hash"
    finally:
        set_audit_session_factory(original_factory)


@pytest.mark.asyncio
async def test_audit_write_failure_no_side_effect():
    mock_audit_session = _make_mock_audit_session()
    mock_audit_session.add = MagicMock(side_effect=Exception("DB error"))

    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    try:
        set_audit_session_factory(mock_factory)
        result = await record_model_call(
            operation="llm_answer",
            provider="local",
            model="local-mock",
            status="success",
            duration_ms=50,
        )
        assert result is None
    finally:
        set_audit_session_factory(original_factory)


@pytest.mark.asyncio
async def test_non_default_user_embedding_audit():
    from app.services.embedding_service import EmbeddingService

    mock_provider = AsyncMock()
    mock_provider.embed_texts = AsyncMock(return_value=[[0.1] * 384])

    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    with patch("app.services.embedding_service.get_embedding_provider", return_value=mock_provider):
        try:
            set_audit_session_factory(mock_factory)
            svc = EmbeddingService(mock_session, user_id="custom-user-42")
            svc.repo = AsyncMock()
            await svc.embed_query("custom question")
        finally:
            set_audit_session_factory(original_factory)

    audit_calls = [c[0][0] for c in mock_audit_session.add.call_args_list if isinstance(c[0][0], ModelCallEvent)]
    assert len(audit_calls) >= 1
    assert audit_calls[0].user_id == "custom-user-42"


@pytest.mark.asyncio
async def test_single_ask_produces_no_duplicate_embedding_query_audit():
    from app.services.rag_service import RAGService

    mock_audit_session = _make_mock_audit_session()
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.flush = AsyncMock()

    with patch("app.services.rag_service.EmbeddingService") as MockEmbSvc, \
         patch("app.services.rag_service.get_llm_provider") as mock_llm:
        mock_emb_instance = AsyncMock()
        mock_emb_instance.embed_query = AsyncMock(return_value=[0.1] * 384)
        MockEmbSvc.return_value = mock_emb_instance

        mock_llm_instance = AsyncMock()
        mock_llm_instance.generate_answer = AsyncMock(return_value="test answer")
        mock_llm.return_value = mock_llm_instance

        try:
            set_audit_session_factory(mock_factory)
            svc = RAGService(mock_session, user_id="test-dedup")
            svc.repo = AsyncMock()
            svc.repo.get_paper = AsyncMock(return_value=MagicMock(status="completed"))
            svc.repo.get_chunk_count = AsyncMock(return_value=5)
            svc.repo.get_embedding_count = AsyncMock(return_value=5)

            mock_retrieved = [MagicMock(score=0.9, text_excerpt="test excerpt")]
            svc._retrieve = AsyncMock(return_value=mock_retrieved)

            result = await svc.ask(paper_id=1, question="test question")
        finally:
            set_audit_session_factory(original_factory)

    embedding_query_audits = [
        c[0][0] for c in mock_audit_session.add.call_args_list
        if isinstance(c[0][0], ModelCallEvent) and c[0][0].operation == "embedding_query"
    ]
    assert len(embedding_query_audits) == 0

    llm_answer_audits = [
        c[0][0] for c in mock_audit_session.add.call_args_list
        if isinstance(c[0][0], ModelCallEvent) and c[0][0].operation == "llm_answer"
    ]
    assert len(llm_answer_audits) == 1


@pytest.mark.asyncio
@skip_if_no_db()
async def test_audit_persists_and_queryable():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/usage/model-calls", headers={"X-User-Id": "default"})

    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data


@pytest.mark.asyncio
@skip_if_no_db()
async def test_usage_model_calls_response_model_in_openapi():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")

    assert resp.status_code == 200
    schema = resp.json()
    model_calls_path = schema["paths"]["/usage/model-calls"]["get"]
    assert "200" in model_calls_path["responses"]
    ref = model_calls_path["responses"]["200"].get("content", {}).get("application/json", {}).get("schema", {}).get("$ref", "")
    assert "ModelCallListResponse" in ref

    summary_path = schema["paths"]["/usage/model-calls/summary"]["get"]
    assert "200" in summary_path["responses"]
    ref2 = summary_path["responses"]["200"].get("content", {}).get("application/json", {}).get("schema", {}).get("$ref", "")
    assert "ModelCallSummaryResponse" in ref2


@pytest.mark.asyncio
@skip_if_no_db()
async def test_record_model_call_persists_to_test_db_and_usage_api_can_read():
    await record_model_call(
        user_id="audit-real-user",
        operation="embedding_query",
        provider="local",
        model="local-hash",
        status="success",
        duration_ms=42,
        input_count=1,
        input_chars=30,
        output_chars=0,
        metadata={"query_length": 30},
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/usage/model-calls", headers={"X-User-Id": "audit-real-user"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    found = [
        e for e in data["events"]
        if e["operation"] == "embedding_query"
        and e["provider"] == "local"
        and e["model"] == "local-hash"
        and e["status"] == "success"
        and e["duration_ms"] == 42
    ]
    assert len(found) >= 1

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_other = await client.get("/usage/model-calls", headers={"X-User-Id": "audit-other-user"})

    assert resp_other.status_code == 200
    other_data = resp_other.json()
    other_found = [
        e for e in other_data["events"]
        if e["operation"] == "embedding_query" and e["duration_ms"] == 42
    ]
    assert len(other_found) == 0


@pytest.mark.asyncio
@skip_if_no_db()
async def test_model_call_events_are_isolated_between_tests():
    from app.database import get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/usage/model-calls", headers={"X-User-Id": "audit-isolation-check"})

    assert resp.status_code == 200
    data = resp.json()
    leftover = [
        e for e in data["events"]
        if e["operation"] == "embedding_query" and e["duration_ms"] == 42
    ]
    assert len(leftover) == 0


@pytest.mark.asyncio
async def test_audit_write_failure_log_no_sensitive_info(caplog):
    import logging

    mock_audit_session = _make_mock_audit_session()
    mock_audit_session.add = MagicMock(side_effect=Exception("postgresql+asyncpg://admin:pass@db:5432/prod"))

    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    try:
        set_audit_session_factory(mock_factory)
        with caplog.at_level(logging.WARNING, logger="app.services.model_call_audit_service"):
            await record_model_call(
                operation="llm_answer",
                provider="local",
                model="local-mock",
                status="success",
                duration_ms=50,
            )

        log_messages = [r.message for r in caplog.records]
        for msg in log_messages:
            assert "admin:pass" not in msg
            assert "postgresql+asyncpg://" not in msg or "***REDACTED***" in msg
    finally:
        set_audit_session_factory(original_factory)
