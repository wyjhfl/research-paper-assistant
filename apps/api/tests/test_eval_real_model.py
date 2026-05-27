from __future__ import annotations

import json
import os
import re
import pytest
from pathlib import Path
from unittest.mock import patch

from app.config import settings


def _save_settings():
    return {
        "REAL_MODEL_REQUIRED": settings.REAL_MODEL_REQUIRED,
        "LLM_PROVIDER": settings.LLM_PROVIDER,
        "LLM_MODEL": settings.LLM_MODEL,
        "LLM_API_KEY": settings.LLM_API_KEY,
        "LLM_BASE_URL": settings.LLM_BASE_URL,
        "EMBEDDING_PROVIDER": settings.EMBEDDING_PROVIDER,
        "EMBEDDING_MODEL": settings.EMBEDDING_MODEL,
        "EMBEDDING_API_KEY": settings.EMBEDDING_API_KEY,
        "EMBEDDING_BASE_URL": settings.EMBEDDING_BASE_URL,
        "EMBEDDING_DIMENSION": settings.EMBEDDING_DIMENSION,
    }


def _restore_settings(saved: dict):
    for k, v in saved.items():
        setattr(settings, k, v)


@pytest.fixture(autouse=True)
def _isolate_settings():
    saved = _save_settings()
    yield
    _restore_settings(saved)


def test_eval_refuses_when_real_model_required_false():
    settings.REAL_MODEL_REQUIRED = False
    settings.LLM_PROVIDER = "openai_compatible"
    settings.EMBEDDING_PROVIDER = "openai_compatible"

    from scripts.eval_real_model import run_eval
    import asyncio

    result = asyncio.get_event_loop().run_until_complete(run_eval())
    assert result == 1


def test_eval_refuses_when_llm_provider_local():
    settings.REAL_MODEL_REQUIRED = True
    settings.LLM_PROVIDER = "local"
    settings.EMBEDDING_PROVIDER = "openai_compatible"

    from scripts.eval_real_model import run_eval
    import asyncio

    result = asyncio.get_event_loop().run_until_complete(run_eval())
    assert result == 1


def test_eval_refuses_when_embedding_provider_local():
    settings.REAL_MODEL_REQUIRED = True
    settings.LLM_PROVIDER = "openai_compatible"
    settings.EMBEDDING_PROVIDER = "local"

    from scripts.eval_real_model import run_eval
    import asyncio

    result = asyncio.get_event_loop().run_until_complete(run_eval())
    assert result == 1


def test_sanitize_dict_redacts_sensitive_keys():
    from scripts.eval_real_model import _sanitize_dict

    data = {
        "api_key": "sk-secret123",
        "authorization": "Bearer token123",
        "normal_field": "hello",
        "nested": {"database_url": "postgres://user:pass@host/db"},
    }
    result = _sanitize_dict(data)
    assert result["api_key"] == "***REDACTED***"
    assert result["authorization"] == "***REDACTED***"
    assert result["normal_field"] == "hello"
    assert result["nested"]["database_url"] == "***REDACTED***"


def test_sanitize_dict_redacts_sensitive_values():
    from scripts.eval_real_model import _sanitize_dict

    saved_url = settings.DATABASE_URL
    settings.DATABASE_URL = "postgresql+asyncpg://secret_user:secret_pass@host/db"
    try:
        data = {"connection": f"Connected to {settings.DATABASE_URL}"}
        result = _sanitize_dict(data)
        assert "secret_user" not in result["connection"]
        assert "secret_pass" not in result["connection"]
        assert "***REDACTED***" in result["connection"]
    finally:
        settings.DATABASE_URL = saved_url


def test_sanitize_dict_redacts_file_path_key():
    from scripts.eval_real_model import _sanitize_dict

    data = {"file_path": "/storage/demo/demo_transformer.pdf"}
    result = _sanitize_dict(data)
    assert result["file_path"] == "***REDACTED***"


def test_sanitize_dict_redacts_postgresql_in_value():
    from scripts.eval_real_model import _sanitize_dict

    data = {"info": "connected to postgresql+asyncpg://host/db"}
    result = _sanitize_dict(data)
    assert result["info"] == "***REDACTED***"


def test_sanitize_dict_redacts_traceback_in_value():
    from scripts.eval_real_model import _sanitize_dict

    data = {"error": "Traceback (most recent call last): File ..."}
    result = _sanitize_dict(data)
    assert result["error"] == "***REDACTED***"


def test_aggregate_results_correct():
    from scripts.eval_real_model import aggregate_results

    cases = [
        {"case_id": "c1", "status": "passed", "severity": "blocker", "warnings": []},
        {"case_id": "c2", "status": "warning", "severity": "warning", "warnings": ["low confidence"]},
        {"case_id": "c3", "status": "failed", "severity": "blocker", "warnings": ["no sources"]},
        {"case_id": "c4", "status": "passed", "severity": "blocker", "warnings": []},
    ]
    report = aggregate_results(cases, {})
    assert report["totals"]["total"] == 4
    assert report["totals"]["passed"] == 2
    assert report["totals"]["warning"] == 1
    assert report["totals"]["failed"] == 1
    assert len(report["failed_details"]) == 1
    assert report["failed_details"][0]["case_id"] == "c3"
    assert report["can_proceed"] is False


def test_aggregate_results_all_passed():
    from scripts.eval_real_model import aggregate_results

    cases = [
        {"case_id": "c1", "status": "passed", "severity": "blocker", "warnings": []},
        {"case_id": "c2", "status": "passed", "severity": "blocker", "warnings": []},
    ]
    report = aggregate_results(cases, {})
    assert report["can_proceed"] is True
    assert report["totals"]["failed"] == 0


def test_report_dir_defaults_to_cwd():
    from scripts.eval_real_model import _get_report_dir

    with patch.dict(os.environ, {}, clear=True):
        if "EVAL_REPORT_DIR" in os.environ:
            del os.environ["EVAL_REPORT_DIR"]
        result = _get_report_dir()
        assert result == Path.cwd() / "artifacts" / "evals"


def test_report_dir_uses_eval_report_dir_env():
    from scripts.eval_real_model import _get_report_dir

    custom = "/tmp/custom_eval_output"
    with patch.dict(os.environ, {"EVAL_REPORT_DIR": custom}):
        result = _get_report_dir()
        assert result == Path(custom)


def test_report_file_under_report_dir():
    from scripts.eval_real_model import _get_report_file, _get_report_dir

    with patch.dict(os.environ, {}, clear=True):
        if "EVAL_REPORT_DIR" in os.environ:
            del os.environ["EVAL_REPORT_DIR"]
        report_file = _get_report_file()
        report_dir = _get_report_dir()
        assert report_file == report_dir / "real_model_eval_latest.json"


def test_write_report_writes_latest_and_history(tmp_path, monkeypatch):
    from scripts.eval_real_model import _write_report

    target_dir = tmp_path / "evals"
    monkeypatch.setenv("EVAL_REPORT_DIR", str(target_dir))

    report = {"totals": {"total": 1, "passed": 1, "warning": 0, "failed": 0}, "cases": [], "timestamp": "2026-01-01T00:00:00+00:00"}
    latest_path, history_path = _write_report(report)

    assert latest_path == target_dir / "real_model_eval_latest.json"
    assert latest_path.exists()

    assert history_path.parent == target_dir / "history"
    assert history_path.exists()
    assert re.match(r"real_model_eval_\d{8}_\d{6}_\d{6}\.json", history_path.name)

    with open(latest_path, encoding="utf-8") as f:
        latest_data = json.load(f)
    assert latest_data["totals"]["total"] == 1

    with open(history_path, encoding="utf-8") as f:
        history_data = json.load(f)
    assert history_data["totals"]["total"] == 1


def test_history_filename_format_with_microseconds():
    from scripts.eval_real_model import _get_history_file

    history_file = _get_history_file()
    assert re.match(r"real_model_eval_\d{8}_\d{6}_\d{6}\.json", history_file.name)


def test_history_file_unique_across_rapid_calls():
    from scripts.eval_real_model import _get_history_file

    paths = set()
    for _ in range(10):
        paths.add(str(_get_history_file()))
    assert len(paths) == 10


def test_history_dir_under_report_dir():
    from scripts.eval_real_model import _get_history_dir, _get_report_dir

    with patch.dict(os.environ, {"EVAL_REPORT_DIR": "/tmp/test_eval"}):
        assert _get_history_dir() == _get_report_dir() / "history"


def test_eval_report_dir_overrides_history_path(tmp_path, monkeypatch):
    from scripts.eval_real_model import _get_history_dir, _get_report_dir

    custom = str(tmp_path / "custom_reports")
    monkeypatch.setenv("EVAL_REPORT_DIR", custom)

    assert _get_report_dir() == Path(custom)
    assert _get_history_dir() == Path(custom) / "history"


def test_trend_first_run_no_previous():
    from scripts.eval_real_model import _build_trend_summary

    current = {"totals": {"passed": 6, "warning": 0, "failed": 0}, "cases": []}
    trend = _build_trend_summary(current, [])
    assert trend["previous_report_count"] == 0
    assert trend["previous_latest_timestamp"] is None
    assert trend["passed_delta"] == 0
    assert trend["warning_delta"] == 0
    assert trend["failed_delta"] == 0
    assert trend["case_status_changes"] == []


def test_trend_with_previous_report():
    from scripts.eval_real_model import _build_trend_summary

    previous = [{
        "timestamp": "2026-01-01T00:00:00+00:00",
        "totals": {"passed": 5, "warning": 1, "failed": 0},
        "cases": [
            {"case_id": "c1", "status": "passed"},
            {"case_id": "c2", "status": "warning"},
        ],
    }]
    current = {
        "totals": {"passed": 6, "warning": 0, "failed": 0},
        "cases": [
            {"case_id": "c1", "status": "passed"},
            {"case_id": "c2", "status": "passed"},
        ],
    }
    trend = _build_trend_summary(current, previous)
    assert trend["previous_report_count"] == 1
    assert trend["passed_delta"] == 1
    assert trend["warning_delta"] == -1
    assert trend["failed_delta"] == 0
    assert len(trend["case_status_changes"]) == 1
    assert trend["case_status_changes"][0]["case_id"] == "c2"
    assert trend["case_status_changes"][0]["previous"] == "warning"
    assert trend["case_status_changes"][0]["current"] == "passed"


def test_trend_no_status_changes():
    from scripts.eval_real_model import _build_trend_summary

    previous = [{
        "timestamp": "2026-01-01T00:00:00+00:00",
        "totals": {"passed": 6, "warning": 0, "failed": 0},
        "cases": [
            {"case_id": "c1", "status": "passed"},
        ],
    }]
    current = {
        "totals": {"passed": 6, "warning": 0, "failed": 0},
        "cases": [
            {"case_id": "c1", "status": "passed"},
        ],
    }
    trend = _build_trend_summary(current, previous)
    assert trend["case_status_changes"] == []


def test_load_previous_history_returns_empty_when_no_dir(tmp_path):
    from scripts.eval_real_model import _load_previous_history_reports

    result = _load_previous_history_reports(tmp_path / "nonexistent")
    assert result == []


def test_load_previous_history_loads_valid_files(tmp_path):
    from scripts.eval_real_model import _load_previous_history_reports

    history_dir = tmp_path / "history"
    history_dir.mkdir()

    for name in ["real_model_eval_20260101_000000_000000.json", "real_model_eval_20260102_000000_000000.json"]:
        with open(history_dir / name, "w") as f:
            json.dump({"timestamp": name, "totals": {"passed": 6}, "cases": []}, f)

    result = _load_previous_history_reports(tmp_path, limit=5)
    assert len(result) == 2
    assert result[0]["timestamp"] == "real_model_eval_20260102_000000_000000.json"


def test_load_previous_history_skips_corrupt_json(tmp_path):
    from scripts.eval_real_model import _load_previous_history_reports

    history_dir = tmp_path / "history"
    history_dir.mkdir()

    with open(history_dir / "real_model_eval_20260101_000000_000000.json", "w") as f:
        json.dump({"timestamp": "ok", "totals": {"passed": 6}, "cases": []}, f)

    with open(history_dir / "real_model_eval_20260102_000000_000000.json", "w") as f:
        f.write("{invalid json")

    result = _load_previous_history_reports(tmp_path, limit=5)
    assert len(result) == 1


def test_load_previous_history_continues_past_corrupt(tmp_path):
    from scripts.eval_real_model import _load_previous_history_reports

    history_dir = tmp_path / "history"
    history_dir.mkdir()

    with open(history_dir / "real_model_eval_20260103_000000_000000.json", "w") as f:
        f.write("{invalid json")

    with open(history_dir / "real_model_eval_20260102_000000_000000.json", "w") as f:
        json.dump({"timestamp": "valid_2", "totals": {"passed": 5}, "cases": []}, f)

    with open(history_dir / "real_model_eval_20260101_000000_000000.json", "w") as f:
        json.dump({"timestamp": "valid_1", "totals": {"passed": 4}, "cases": []}, f)

    result = _load_previous_history_reports(tmp_path, limit=5)
    assert len(result) == 2
    assert result[0]["timestamp"] == "valid_2"
    assert result[1]["timestamp"] == "valid_1"


def test_load_previous_history_respects_limit(tmp_path):
    from scripts.eval_real_model import _load_previous_history_reports

    history_dir = tmp_path / "history"
    history_dir.mkdir()

    for i in range(5):
        name = f"real_model_eval_2026010{i+1}_000000_000000.json"
        with open(history_dir / name, "w") as f:
            json.dump({"timestamp": name, "totals": {"passed": 6}, "cases": []}, f)

    result = _load_previous_history_reports(tmp_path, limit=3)
    assert len(result) == 3


def test_current_report_not_treated_as_previous(tmp_path, monkeypatch):
    from scripts.eval_real_model import (
        _load_previous_history_reports,
        _build_trend_summary,
        _write_report,
    )

    monkeypatch.setenv("EVAL_REPORT_DIR", str(tmp_path))

    prev_ts = "2026-01-01T00:00:00+00:00"
    prev_report = {
        "totals": {"total": 1, "passed": 1, "warning": 0, "failed": 0},
        "cases": [{"case_id": "c1", "status": "passed"}],
        "timestamp": prev_ts,
    }
    _write_report(prev_report)

    previous_before = _load_previous_history_reports(tmp_path, limit=5)
    assert len(previous_before) == 1
    assert previous_before[0]["timestamp"] == prev_ts

    current_ts = "2026-01-02T00:00:00+00:00"
    current_report = {
        "totals": {"total": 1, "passed": 1, "warning": 0, "failed": 0},
        "cases": [{"case_id": "c1", "status": "passed"}],
        "timestamp": current_ts,
    }

    trend = _build_trend_summary(current_report, previous_before)
    assert trend["previous_latest_timestamp"] == prev_ts
    assert trend["previous_latest_timestamp"] != current_ts
    assert trend["previous_report_count"] == 1


def test_history_report_is_sanitized(tmp_path, monkeypatch):
    from scripts.eval_real_model import _write_report

    monkeypatch.setenv("EVAL_REPORT_DIR", str(tmp_path))

    saved_url = settings.DATABASE_URL
    settings.DATABASE_URL = "postgresql+asyncpg://secret_user:secret_pass@host/db"
    try:
        report = {
            "totals": {"total": 1, "passed": 1, "warning": 0, "failed": 0},
            "cases": [], "timestamp": "2026-01-01T00:00:00+00:00",
            "connection": f"Connected to {settings.DATABASE_URL}",
        }
        _, history_path = _write_report(report)

        with open(history_path, encoding="utf-8") as f:
            content = f.read()
        assert "secret_user" not in content
        assert "secret_pass" not in content
    finally:
        settings.DATABASE_URL = saved_url


def test_report_path_contains_artifacts_evals():
    from scripts.eval_real_model import _get_report_dir

    with patch.dict(os.environ, {}, clear=True):
        if "EVAL_REPORT_DIR" in os.environ:
            del os.environ["EVAL_REPORT_DIR"]
        result = _get_report_dir()
        assert "artifacts" in str(result)
        assert "evals" in str(result)


def test_truncate_preview():
    from scripts.eval_real_model import _truncate_preview

    assert _truncate_preview(None) == ""
    assert _truncate_preview("") == ""
    assert _truncate_preview("short") == "short"
    long_text = "a" * 300
    result = _truncate_preview(long_text)
    assert len(result) <= 203
    assert result.endswith("...")


def test_no_sensitive_output_check():
    from scripts.eval_real_model import _check_no_sensitive_output

    clean = {"answer": "Attention is used for token relations", "sources": []}
    assert _check_no_sensitive_output(clean) is True

    dirty = {"answer": f"key={settings.LLM_API_KEY}", "sources": []}
    if settings.LLM_API_KEY:
        assert _check_no_sensitive_output(dirty) is False


def test_no_sensitive_output_detects_file_path():
    from scripts.eval_real_model import _check_no_sensitive_output

    data = {"info": "file_path is present"}
    assert _check_no_sensitive_output(data) is False


def test_no_sensitive_output_detects_traceback():
    from scripts.eval_real_model import _check_no_sensitive_output

    data = {"error": "Traceback (most recent call last)"}
    assert _check_no_sensitive_output(data) is False


def test_no_sensitive_output_detects_postgresql():
    from scripts.eval_real_model import _check_no_sensitive_output

    data = {"url": "postgresql+asyncpg://user:pass@host/db"}
    assert _check_no_sensitive_output(data) is False


def test_no_sensitive_output_detects_database_url():
    from scripts.eval_real_model import _check_no_sensitive_output

    data = {"config": "DATABASE_URL=something"}
    assert _check_no_sensitive_output(data) is False


def test_no_sensitive_output_detects_authorization():
    from scripts.eval_real_model import _check_no_sensitive_output

    data = {"header": "Authorization: Bearer token"}
    assert _check_no_sensitive_output(data) is False
