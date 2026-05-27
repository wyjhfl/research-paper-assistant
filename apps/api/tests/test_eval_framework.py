from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from eval_real_model import (
    _check_no_sensitive_output,
    _load_previous_history_reports,
    _sanitize_dict,
    aggregate_results,
    assert_eval_result,
    load_eval_cases,
    validate_eval_case_schema,
)

_CASES_DIR = Path(__file__).resolve().parent.parent / "evals"
_REAL_CASES_PATH = _CASES_DIR / "real_model_cases.json"


def _write_temp_cases(cases: list[dict], tmp: Path) -> Path:
    p = tmp / "cases.json"
    p.write_text(json.dumps(cases), encoding="utf-8")
    return p


class TestLoadEvalCases:
    def test_load_valid_cases(self):
        cases = load_eval_cases(_REAL_CASES_PATH)
        assert isinstance(cases, list)
        assert len(cases) >= 12

    def test_load_from_temp_file(self, tmp_path):
        cases_data = [
            {
                "case_id": "test_1",
                "type": "single_rag",
                "description": "test",
                "input": {"question": "q"},
                "expected": {"min_sources": 1},
                "severity": "blocker",
            }
        ]
        p = _write_temp_cases(cases_data, tmp_path)
        cases = load_eval_cases(p)
        assert len(cases) == 1
        assert cases[0]["case_id"] == "test_1"

    def test_missing_file_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            load_eval_cases(tmp_path / "nonexistent.json")

    def test_invalid_json_exits(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(SystemExit):
            load_eval_cases(p)

    def test_non_array_json_exits(self, tmp_path):
        p = tmp_path / "obj.json"
        p.write_text('{"case_id": "x"}', encoding="utf-8")
        with pytest.raises(SystemExit):
            load_eval_cases(p)


class TestValidateEvalCaseSchema:
    def test_missing_case_id_exits(self):
        with pytest.raises(SystemExit):
            validate_eval_case_schema({"type": "single_rag", "severity": "blocker", "input": {}, "expected": {}})

    def test_missing_type_exits(self):
        with pytest.raises(SystemExit):
            validate_eval_case_schema({"case_id": "x", "severity": "blocker", "input": {}, "expected": {}})

    def test_invalid_type_exits(self):
        with pytest.raises(SystemExit):
            validate_eval_case_schema({"case_id": "x", "type": "invalid_type", "severity": "blocker", "input": {}, "expected": {}})

    def test_missing_severity_exits(self):
        with pytest.raises(SystemExit):
            validate_eval_case_schema({"case_id": "x", "type": "single_rag", "input": {}, "expected": {}})

    def test_invalid_severity_exits(self):
        with pytest.raises(SystemExit):
            validate_eval_case_schema({"case_id": "x", "type": "single_rag", "severity": "critical", "input": {}, "expected": {}})

    def test_missing_input_exits(self):
        with pytest.raises(SystemExit):
            validate_eval_case_schema({"case_id": "x", "type": "single_rag", "severity": "blocker", "expected": {}})

    def test_missing_expected_exits(self):
        with pytest.raises(SystemExit):
            validate_eval_case_schema({"case_id": "x", "type": "single_rag", "severity": "blocker", "input": {}})

    def test_valid_case_passes(self):
        validate_eval_case_schema({
            "case_id": "x", "type": "single_rag", "severity": "blocker",
            "input": {"question": "q"}, "expected": {"min_sources": 1},
        })


class TestAssertEvalResult:
    def _make_case(self, **overrides) -> dict:
        base = {
            "case_id": "test",
            "type": "single_rag",
            "severity": "blocker",
            "input": {"question": "q"},
            "expected": {},
        }
        base.update(overrides)
        return base

    def test_min_sources_pass(self):
        case = self._make_case(expected={"min_sources": 2})
        result = {"source_count": 3, "sources": [], "paper_count": 1}
        out = assert_eval_result(case, result)
        assert out["checks"]["min_sources"] is True
        assert out["status"] == "passed"

    def test_min_sources_fail(self):
        case = self._make_case(expected={"min_sources": 5})
        result = {"source_count": 2, "sources": [], "paper_count": 1}
        out = assert_eval_result(case, result)
        assert out["checks"]["min_sources"] is False
        assert out["status"] == "failed"

    def test_min_distinct_papers_pass(self):
        case = self._make_case(expected={"min_distinct_papers": 2})
        result = {"source_count": 3, "sources": [], "paper_count": 2}
        out = assert_eval_result(case, result)
        assert out["checks"]["min_distinct_papers"] is True

    def test_min_distinct_papers_fail(self):
        case = self._make_case(expected={"min_distinct_papers": 3})
        result = {"source_count": 2, "sources": [], "paper_count": 1}
        out = assert_eval_result(case, result)
        assert out["checks"]["min_distinct_papers"] is False

    def test_forbidden_source_paper_ids_list(self):
        case = self._make_case(expected={"forbidden_source_paper_ids": [99, 100]})
        result = {
            "source_count": 2,
            "sources": [{"paper_id": 1}, {"paper_id": 2}],
            "paper_count": 2,
        }
        out = assert_eval_result(case, result)
        assert out["checks"]["paper_filter_respected"] is True

    def test_forbidden_source_paper_ids_violated(self):
        case = self._make_case(expected={"forbidden_source_paper_ids": [99]})
        result = {
            "source_count": 2,
            "sources": [{"paper_id": 99}, {"paper_id": 1}],
            "paper_count": 2,
        }
        out = assert_eval_result(case, result)
        assert out["checks"]["paper_filter_respected"] is False

    def test_forbidden_source_paper_ids_auto(self):
        case = self._make_case(expected={"forbidden_source_paper_ids": "auto"})
        result = {
            "source_count": 2,
            "sources": [{"paper_id": 1}, {"paper_id": 2}],
            "paper_count": 2,
            "allowed_paper_ids": {1},
        }
        out = assert_eval_result(case, result)
        assert out["checks"]["paper_filter_respected"] is False

    def test_require_paper_title_pass(self):
        case = self._make_case(expected={"require_paper_title": True})
        result = {
            "source_count": 1,
            "sources": [{"paper_id": 1, "paper_title": "Test Paper"}],
            "paper_count": 1,
        }
        out = assert_eval_result(case, result)
        assert out["checks"]["require_paper_title"] is True

    def test_require_paper_title_fail(self):
        case = self._make_case(expected={"require_paper_title": True})
        result = {
            "source_count": 1,
            "sources": [{"paper_id": 1}],
            "paper_count": 1,
        }
        out = assert_eval_result(case, result)
        assert out["checks"]["require_paper_title"] is False

    def test_blocker_failed_means_failed(self):
        case = self._make_case(severity="blocker", expected={"min_sources": 10})
        result = {"source_count": 1, "sources": [], "paper_count": 1}
        out = assert_eval_result(case, result)
        assert out["status"] == "failed"
        assert out["severity"] == "blocker"

    def test_warning_failed_means_warning(self):
        case = self._make_case(severity="warning", expected={"min_sources": 10})
        result = {"source_count": 1, "sources": [], "paper_count": 1}
        out = assert_eval_result(case, result)
        assert out["status"] == "warning"
        assert out["severity"] == "warning"

    def test_allowed_rag_status_pass(self):
        case = self._make_case(expected={"allowed_rag_status": ["answered"]})
        result = {"rag_status": "answered", "source_count": 1, "sources": [], "paper_count": 1}
        out = assert_eval_result(case, result)
        assert out["checks"]["rag_status_allowed"] is True

    def test_allowed_rag_status_fail(self):
        case = self._make_case(expected={"allowed_rag_status": ["answered"]})
        result = {"rag_status": "insufficient_context", "source_count": 0, "sources": [], "paper_count": 0}
        out = assert_eval_result(case, result)
        assert out["checks"]["rag_status_allowed"] is False

    def test_duration_ms_recorded(self):
        case = self._make_case()
        result = {"source_count": 0, "sources": [], "paper_count": 0, "duration_ms": 1234}
        out = assert_eval_result(case, result)
        assert out["duration_ms"] == 1234


class TestAggregateResults:
    def test_blocker_failed_means_cannot_proceed(self):
        cases = [
            {"case_id": "a", "status": "passed", "severity": "blocker", "warnings": []},
            {"case_id": "b", "status": "failed", "severity": "blocker", "warnings": ["x"]},
        ]
        report = aggregate_results(cases, {})
        assert report["can_proceed"] is False
        assert report["totals"]["blocker_failed"] == 1

    def test_warning_failed_can_proceed(self):
        cases = [
            {"case_id": "a", "status": "passed", "severity": "blocker", "warnings": []},
            {"case_id": "b", "status": "warning", "severity": "warning", "warnings": ["x"]},
        ]
        report = aggregate_results(cases, {})
        assert report["can_proceed"] is True
        assert report["totals"]["warning"] == 1
        assert report["totals"]["blocker_failed"] == 0

    def test_metadata_included(self):
        cases = []
        meta = {"llm_model": "test-model", "embedding_dimension": 1024}
        report = aggregate_results(cases, meta)
        assert report["metadata"]["llm_model"] == "test-model"

    def test_totals_structure(self):
        cases = [
            {"case_id": "a", "status": "passed", "severity": "blocker", "warnings": []},
            {"case_id": "b", "status": "warning", "severity": "warning", "warnings": []},
            {"case_id": "c", "status": "failed", "severity": "blocker", "warnings": ["err"]},
        ]
        report = aggregate_results(cases, {})
        t = report["totals"]
        assert t["total"] == 3
        assert t["passed"] == 1
        assert t["warning"] == 1
        assert t["failed"] == 1
        assert t["blocker_failed"] == 1


class TestSanitizeReport:
    def test_api_key_value_redacted(self):
        report = {
            "metadata": {"llm_model": "test"},
            "cases": [{"api_key": "sk-abc123def456ghi789"}],
        }
        sanitized = _sanitize_dict(report)
        raw = json.dumps(sanitized)
        assert "sk-abc123" not in raw
        assert "***REDACTED***" in raw

    def test_authorization_value_redacted(self):
        report = {
            "cases": [{"authorization": "Bearer secret-token-12345"}],
        }
        sanitized = _sanitize_dict(report)
        raw = json.dumps(sanitized)
        assert "secret-token-12345" not in raw

    def test_database_url_value_redacted(self):
        report = {
            "cases": [{"database_url": "postgresql+asyncpg://user:pass@host/db"}],
        }
        sanitized = _sanitize_dict(report)
        raw = json.dumps(sanitized)
        assert "postgresql+asyncpg://user:pass" not in raw

    def test_traceback_redacted(self):
        report = {
            "cases": [{"detail": "Traceback (most recent call last):"}],
        }
        sanitized = _sanitize_dict(report)
        raw = json.dumps(sanitized)
        assert "Traceback" not in raw

    def test_sensitive_settings_values_redacted(self):
        with patch("eval_real_model._get_sensitive_values", return_value={"sk-secretkey123"}):
            report = {
                "cases": [{"answer_preview": "the key is sk-secretkey123 in output"}],
            }
            sanitized = _sanitize_dict(report)
            raw = json.dumps(sanitized)
            assert "sk-secretkey123" not in raw


class TestCorruptedHistoryReports:
    def test_corrupted_history_skipped(self, tmp_path):
        history_dir = tmp_path / "history"
        history_dir.mkdir()
        bad_file = history_dir / "real_model_eval_20260101_000000_000000.json"
        bad_file.write_text("not valid json{{{", encoding="utf-8")
        good_file = history_dir / "real_model_eval_20260102_000000_000000.json"
        good_file.write_text(json.dumps({"timestamp": "2026-01-02T00:00:00", "cases": []}), encoding="utf-8")

        reports = _load_previous_history_reports(tmp_path, limit=5)
        assert len(reports) == 1
        assert reports[0]["timestamp"] == "2026-01-02T00:00:00"
