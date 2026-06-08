from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "personal_workflow_smoke.py"


def load_module():
    spec = importlib.util.spec_from_file_location("personal_workflow_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestPersonalWorkflowSmokeStaticSafety:
    def test_script_exists(self):
        assert SCRIPT.exists()

    def test_script_does_not_run_destructive_or_secret_operations(self):
        content = SCRIPT.read_text(encoding="utf-8")
        forbidden = [
            "eval_real_model.py",
            "restore_all",
            "restore_postgres",
            "restore_storage",
            "backup_all",
            "--confirm",
            "git push",
            "git tag",
            ".env",
            "LLM_API_KEY",
            "EMBEDDING_API_KEY",
            "Authorization",
        ]
        for token in forbidden:
            assert token not in content


class TestPersonalWorkflowSmokeRuntime:
    def test_full_workflow_smoke_writes_note_when_explicitly_enabled(self, monkeypatch, capsys):
        module = load_module()
        calls: list[tuple[str, str, dict | None]] = []
        note_written = False

        def fake_request_json(api_base, method, path, body=None, user_id="default", timeout=30):
            nonlocal note_written
            calls.append((method, path, body))
            if method == "GET" and path == "/health/ready":
                return True, {"ready": True, "database": "connected"}
            if method == "GET" and path == "/papers":
                return True, {
                    "papers": [
                        {"id": 1, "title": "Short", "status": "completed", "chunk_count": 1},
                        {"id": 2, "title": "Richer Paper", "status": "completed", "chunk_count": 5},
                    ]
                }
            if method == "POST" and path == "/papers/2/ask":
                assert body == {
                    "question": "What method or contribution does this paper propose?",
                    "allow_low_confidence_answer": True,
                }
                return True, {"status": "answered", "confidence": 0.42, "sources": [{"chunk_id": 10}]}
            if method == "POST" and path == "/papers/review-matrix":
                return True, {"rows": [{"paper_id": 2, "paper_title": "Richer Paper"}], "total_papers": 1}
            if method == "POST" and path == "/notes":
                assert body
                assert body["note_type"] == "manual"
                assert "local-workflow-smoke" in body["tags"]
                note_written = True
                return True, {"note": {"id": 9, "title": body["title"], "content": body["content"]}}
            if method == "GET" and path == "/notes":
                if note_written:
                    return True, {"notes": [{"id": 9, "title": "Personal workflow smoke note", "tags": ["local-workflow-smoke"]}], "total": 1}
                return True, {"notes": [], "total": 0}
            raise AssertionError((method, path))

        monkeypatch.setattr(module, "_request_json", fake_request_json)

        assert module.main(["--write-note"]) == 0
        out = json.loads(capsys.readouterr().out)

        assert out["ok"] is True
        assert out["selected_paper_id"] == 2
        assert any(c["name"] == "single paper qa" and c["ok"] for c in out["checks"])
        assert any(c["name"] == "review matrix" and "rows=1" in c["message"] for c in out["checks"])
        assert any(c["name"] == "research note save" and "note_id=9" in c["message"] for c in out["checks"])
        assert ("POST", "/notes",) == calls[-2][:2]

    def test_write_note_reuses_existing_smoke_note(self, monkeypatch, capsys):
        module = load_module()
        calls: list[tuple[str, str]] = []

        def fake_request_json(api_base, method, path, body=None, user_id="default", timeout=30):
            calls.append((method, path))
            if path == "/health/ready":
                return True, {"ready": True}
            if path == "/papers":
                return True, {"papers": [{"id": 3, "title": "Paper", "status": "completed", "chunk_count": 2}]}
            if path == "/papers/3/ask":
                return True, {"status": "answered", "confidence": 0.3, "sources": [{"chunk_id": 1}]}
            if path == "/papers/review-matrix":
                return True, {"rows": [{"paper_id": 3}], "total_papers": 1}
            if method == "GET" and path == "/notes":
                return True, {
                    "notes": [{"id": 11, "title": "Personal workflow smoke note", "tags": ["local-workflow-smoke"]}],
                    "total": 1,
                }
            raise AssertionError((method, path))

        monkeypatch.setattr(module, "_request_json", fake_request_json)

        assert module.main(["--write-note"]) == 0
        out = json.loads(capsys.readouterr().out)

        assert not any(method == "POST" and path == "/notes" for method, path in calls)
        assert any(c["name"] == "research note save" and "existing_note_id=11" in c["message"] for c in out["checks"])

    def test_note_write_is_skipped_by_default(self, monkeypatch, capsys):
        module = load_module()
        paths: list[str] = []

        def fake_request_json(api_base, method, path, body=None, user_id="default", timeout=30):
            paths.append(path)
            if path == "/health/ready":
                return True, {"ready": True}
            if path == "/papers":
                return True, {"papers": [{"id": 3, "title": "Paper", "status": "completed", "chunk_count": 2}]}
            if path == "/papers/3/ask":
                return True, {"status": "low_confidence_answer", "confidence": 0.2, "sources": [{"chunk_id": 1}]}
            if path == "/papers/review-matrix":
                return True, {"rows": [{"paper_id": 3}], "total_papers": 1}
            raise AssertionError(path)

        monkeypatch.setattr(module, "_request_json", fake_request_json)

        assert module.main([]) == 0
        out = json.loads(capsys.readouterr().out)

        assert out["ok"] is True
        assert "/notes" not in paths
        assert any(c["name"] == "research note save" and c["ok"] and "skipped" in c["message"] for c in out["checks"])
