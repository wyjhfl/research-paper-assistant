from __future__ import annotations

import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from httpx import AsyncClient, ASGITransport

from app.main import app

try:
    from conftest import _db_available as __db_avail
except ImportError:
    __db_avail = False

skip_if_no_db = pytest.mark.skipif(
    not __db_avail,
    reason="PostgreSQL not available for test DB",
)


def _sample_eval_report():
    return {
        "timestamp": "2025-05-24T10:00:00+00:00",
        "can_proceed": True,
        "metadata": {
            "llm_model": "gpt-4",
            "embedding_model": "text-embedding-3-small",
            "embedding_dimension": 1536,
            "case_file": "/app/evals/real_model_cases.json",
        },
        "totals": {
            "total": 5,
            "passed": 4,
            "warning": 1,
            "failed": 0,
            "blocker_failed": 0,
        },
        "trend": {
            "previous_report_count": 1,
            "previous_latest_timestamp": "2025-05-23T10:00:00+00:00",
            "passed_delta": 1,
            "warning_delta": 0,
            "failed_delta": -1,
        },
        "cases": [
            {
                "case_id": "single_rag_basic",
                "type": "single_rag",
                "severity": "blocker",
                "status": "passed",
                "duration_ms": 1200,
                "warnings": [],
            },
            {
                "case_id": "multi_rag_filter",
                "type": "multi_rag",
                "severity": "blocker",
                "status": "passed",
                "duration_ms": 800,
                "warnings": [],
            },
            {
                "case_id": "agent_citation",
                "type": "agent",
                "severity": "warning",
                "status": "warning",
                "duration_ms": 1500,
                "warnings": ["confidence below threshold"],
            },
        ],
    }


@pytest.mark.asyncio
async def test_eval_report_latest_returns_summary_when_report_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"
        report_path.write_text(json.dumps(_sample_eval_report()), encoding="utf-8")

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 200
        data = resp.json()
        assert data["can_proceed"] is True
        assert data["timestamp"] == "2025-05-24T10:00:00+00:00"
        assert data["totals"]["total"] == 5
        assert data["totals"]["passed"] == 4
        assert data["totals"]["failed"] == 0
        assert len(data["cases"]) == 3
        assert data["cases"][0]["case_id"] == "single_rag_basic"
        assert data["cases"][0]["status"] == "passed"
        assert data["metadata"]["llm_model"] == "gpt-4"
        assert data["metadata"]["embedding_model"] == "text-embedding-3-small"
        assert data["trend"]["previous_report_count"] == 1


@pytest.mark.asyncio
async def test_eval_report_latest_returns_404_when_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data


@pytest.mark.asyncio
async def test_eval_report_latest_returns_404_for_invalid_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"
        report_path.write_text("not valid json {{{", encoding="utf-8")

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_eval_report_latest_no_path_traversal():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/usage/eval-report/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code in (404, 405, 422)


@pytest.mark.asyncio
async def test_eval_report_latest_no_sensitive_fields():
    report_data = _sample_eval_report()
    report_data["metadata"]["case_file"] = "/etc/secrets/database_url"
    report_data["cases"][0]["warnings"] = [
        "api_key=sk-secret12345678 found in output",
        "postgresql+asyncpg://admin:pass@db:5432/prod",
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"
        report_path.write_text(json.dumps(report_data), encoding="utf-8")

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 200
        data = resp.json()
        raw = json.dumps(data)
        assert "sk-secret12345678" not in raw
        assert "admin:pass" not in raw
        assert "postgresql+asyncpg://" not in raw or "***REDACTED***" in raw
        assert "/etc/secrets/" not in data["metadata"]["case_file"]


@pytest.mark.asyncio
async def test_eval_report_latest_in_openapi():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")

    assert resp.status_code == 200
    schema = resp.json()
    path_obj = schema["paths"].get("/usage/eval-report/latest", {})
    assert "get" in path_obj
    get_obj = path_obj["get"]
    assert "200" in get_obj["responses"]
    ref = (
        get_obj["responses"]["200"]
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref", "")
    )
    assert "EvalReportSummaryResponse" in ref


@pytest.mark.asyncio
async def test_eval_report_latest_no_answer_preview_or_raw_output():
    report_data = _sample_eval_report()
    report_data["cases"][0]["sanitized_preview"] = "This is a long answer preview that should not be returned by the API endpoint"
    report_data["cases"][0]["checks"] = {"rag_status_allowed": True}
    report_data["cases"][0]["confidence"] = 0.95
    report_data["cases"][0]["source_count"] = 3
    report_data["failed_details"] = [{"case_id": "x", "reason": "failed"}]

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"
        report_path.write_text(json.dumps(report_data), encoding="utf-8")

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 200
        data = resp.json()
        for case in data["cases"]:
            assert "sanitized_preview" not in case
            assert "checks" not in case
            assert "confidence" not in case
            assert "source_count" not in case
        assert "failed_details" not in data


@pytest.mark.asyncio
async def test_eval_report_redacts_bare_sk_token():
    report_data = _sample_eval_report()
    report_data["metadata"]["llm_model"] = "sk-abcdefghijklmnop1234567890"
    report_data["cases"][0]["warnings"] = ["key found: sk-XYZWVUTSRQP987654321"]

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"
        report_path.write_text(json.dumps(report_data), encoding="utf-8")

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 200
        raw = json.dumps(resp.json())
        assert "sk-abcdefghijklmnop1234567890" not in raw
        assert "sk-XYZWVUTSRQP987654321" not in raw
        assert "sk-***REDACTED***" in raw


@pytest.mark.asyncio
async def test_eval_report_redacts_bare_tp_token():
    report_data = _sample_eval_report()
    report_data["metadata"]["embedding_model"] = "tp-abcdefghijklmnop1234567890"
    report_data["cases"][1]["warnings"] = ["tp-ABCDEFGH12345678 detected"]

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"
        report_path.write_text(json.dumps(report_data), encoding="utf-8")

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 200
        raw = json.dumps(resp.json())
        assert "tp-abcdefghijklmnop1234567890" not in raw
        assert "tp-ABCDEFGH12345678" not in raw
        assert "tp-***REDACTED***" in raw


@pytest.mark.asyncio
async def test_eval_report_sanitizes_case_identity_fields():
    report_data = _sample_eval_report()
    report_data["cases"][0]["case_id"] = "sk-CaseSecret123456789"
    report_data["cases"][0]["type"] = "postgresql+asyncpg://admin:pass@db:5432/prod"
    report_data["cases"][0]["severity"] = "Bearer abcdefghijklmnop"
    report_data["cases"][0]["status"] = "api_key=sk-LeakedKey123456789"

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"
        report_path.write_text(json.dumps(report_data), encoding="utf-8")

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 200
        raw = json.dumps(resp.json())
        assert "sk-CaseSecret123456789" not in raw
        assert "admin:pass" not in raw
        assert "Bearer abcdefghijklmnop" not in raw
        assert "sk-LeakedKey123456789" not in raw


@pytest.mark.asyncio
async def test_eval_report_sanitizes_metadata_models():
    report_data = _sample_eval_report()
    report_data["metadata"]["llm_model"] = "Bearer sk-SecretModelKey1234567890"
    report_data["metadata"]["embedding_model"] = "postgresql+asyncpg://user:pw@host/db"

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "real_model_eval_latest.json"
        report_path.write_text(json.dumps(report_data), encoding="utf-8")

        with patch("app.routers.usage._get_eval_report_path", return_value=report_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/usage/eval-report/latest")

        assert resp.status_code == 200
        data = resp.json()
        raw = json.dumps(data)
        assert "sk-SecretModelKey1234567890" not in raw
        assert "user:pw" not in raw
        assert "postgresql+asyncpg://user:pw@host/db" not in raw
