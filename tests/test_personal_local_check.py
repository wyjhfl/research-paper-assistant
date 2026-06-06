from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "personal_local_check.py"
PS_SCRIPT = PROJECT_ROOT / "scripts" / "personal_local_check.ps1"


def load_module():
    spec = importlib.util.spec_from_file_location("personal_local_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestPersonalLocalCheckStaticSafety:
    def test_script_exists(self):
        assert SCRIPT.exists()
        assert PS_SCRIPT.exists()

    def test_no_dangerous_operations(self):
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
            "docker compose up",
            "docker-compose up",
        ]
        for token in forbidden:
            assert token not in content

    def test_uses_resolve_git_not_bare_git_for_git_commands(self):
        content = SCRIPT.read_text(encoding="utf-8")
        assert "def resolve_git" in content
        assert '[\"git\"' not in content
        assert "['git'" not in content

    def test_does_not_print_env_or_secret_values(self):
        content = SCRIPT.read_text(encoding="utf-8")
        assert "read_text" not in content
        assert "LLM_API_KEY" not in content
        assert "EMBEDDING_API_KEY" not in content
        assert ".env" in content  # only path tracking check

    def test_powershell_wrapper_resolves_python_structured(self):
        content = PS_SCRIPT.read_text(encoding="utf-8")
        assert "Resolve-PythonCommand" in content
        assert "Test-PythonCandidate" in content
        assert "@($python.Args + $scriptArgs)" in content
        assert "& \"py -3\"" not in content
        assert "eval_real_model.py" not in content


class TestPersonalLocalCheckRuntime:
    def test_main_success_with_mocked_checks(self, monkeypatch, capsys):
        module = load_module()

        def fake_run(args, timeout=60):
            cmd = " ".join(args)
            if "ls-files" in cmd:
                return subprocess.CompletedProcess(args, 0, "", "")
            if "status --short" in cmd:
                return subprocess.CompletedProcess(args, 0, "", "")
            if "docker --version" in cmd:
                return subprocess.CompletedProcess(args, 0, "Docker version test", "")
            if "docker compose ps" in cmd:
                service_rows = "\n".join([
                    '{"Service":"backend","State":"running","Health":"healthy"}',
                    '{"Service":"frontend","State":"running","Health":""}',
                    '{"Service":"postgres","State":"running","Health":"healthy"}',
                ])
                return subprocess.CompletedProcess(args, 0, service_rows, "")
            if "smoke_check.py" in cmd:
                return subprocess.CompletedProcess(args, 0, "RESULT: ALL CHECKS PASSED", "")
            if "model_smoke_check.py" in cmd:
                return subprocess.CompletedProcess(args, 0, "RESULT: ALL CHECKS PASSED", "")
            if "check_docs_secrets.py" in cmd or "check_frontend_mojibake.py" in cmd:
                return subprocess.CompletedProcess(args, 0, "PASSED", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(module, "_run", fake_run)
        monkeypatch.setattr(module, "_http_json", lambda api_base, path, timeout=10: (True, '{"status": "ok", "ready": true}'))
        monkeypatch.setattr(module, "_http_status", lambda url, timeout=10: (True, "status=200"))
        monkeypatch.setattr(module, "resolve_git", lambda: "git")

        assert module.main([]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is True

    def test_main_fails_when_sensitive_path_tracked(self, monkeypatch, capsys):
        module = load_module()

        def fake_run(args, timeout=60):
            cmd = " ".join(args)
            if "ls-files" in cmd:
                return subprocess.CompletedProcess(args, 0, ".env\n", "")
            if "status --short" in cmd:
                return subprocess.CompletedProcess(args, 0, "", "")
            if "docker --version" in cmd:
                return subprocess.CompletedProcess(args, 0, "Docker version test", "")
            if "docker compose ps" in cmd:
                service_rows = "\n".join([
                    '{"Service":"backend","State":"running","Health":"healthy"}',
                    '{"Service":"frontend","State":"running","Health":""}',
                    '{"Service":"postgres","State":"running","Health":"healthy"}',
                ])
                return subprocess.CompletedProcess(args, 0, service_rows, "")
            if "smoke_check.py" in cmd or "model_smoke_check.py" in cmd:
                return subprocess.CompletedProcess(args, 0, "RESULT: ALL CHECKS PASSED", "")
            return subprocess.CompletedProcess(args, 0, "PASSED", "")

        monkeypatch.setattr(module, "_run", fake_run)
        monkeypatch.setattr(module, "_http_json", lambda api_base, path, timeout=10: (True, '{"status": "ok", "ready": true}'))
        monkeypatch.setattr(module, "_http_status", lambda url, timeout=10: (True, "status=200"))
        monkeypatch.setattr(module, "resolve_git", lambda: "git")

        assert module.main([]) == 1
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is False
        assert any(c["name"] == "git sensitive paths not tracked" and not c["ok"] for c in out["checks"])

    def test_default_skips_model_smoke(self, monkeypatch, capsys):
        module = load_module()
        commands: list[str] = []

        def fake_run(args, timeout=60):
            cmd = " ".join(args)
            commands.append(cmd)
            if "ls-files" in cmd or "status --short" in cmd:
                return subprocess.CompletedProcess(args, 0, "", "")
            if "docker --version" in cmd:
                return subprocess.CompletedProcess(args, 0, "Docker version test", "")
            if "docker compose ps" in cmd:
                service_rows = "\n".join([
                    '{"Service":"backend","State":"running","Health":"healthy"}',
                    '{"Service":"frontend","State":"running","Health":""}',
                    '{"Service":"postgres","State":"running","Health":"healthy"}',
                ])
                return subprocess.CompletedProcess(args, 0, service_rows, "")
            if "smoke_check.py" in cmd:
                return subprocess.CompletedProcess(args, 0, "RESULT: ALL CHECKS PASSED", "")
            return subprocess.CompletedProcess(args, 0, "PASSED", "")

        monkeypatch.setattr(module, "_run", fake_run)
        monkeypatch.setattr(module, "_http_json", lambda api_base, path, timeout=10: (True, '{"status": "ok", "ready": true}'))
        monkeypatch.setattr(module, "_http_status", lambda url, timeout=10: (True, "status=200"))
        monkeypatch.setattr(module, "resolve_git", lambda: "git")

        assert module.main([]) == 0
        assert not any("model_smoke_check.py" in cmd for cmd in commands)
        out = json.loads(capsys.readouterr().out)
        assert any(c["name"] == "backend model_smoke_check.py" and "skipped" in c["message"] for c in out["checks"])

    def test_run_model_smoke_executes_model_command(self, monkeypatch, capsys):
        module = load_module()
        commands: list[str] = []

        def fake_run(args, timeout=60):
            cmd = " ".join(args)
            commands.append(cmd)
            if "ls-files" in cmd or "status --short" in cmd:
                return subprocess.CompletedProcess(args, 0, "", "")
            if "docker --version" in cmd:
                return subprocess.CompletedProcess(args, 0, "Docker version test", "")
            if "docker compose ps" in cmd:
                service_rows = "\n".join([
                    '{"Service":"backend","State":"running","Health":"healthy"}',
                    '{"Service":"frontend","State":"running","Health":""}',
                    '{"Service":"postgres","State":"running","Health":"healthy"}',
                ])
                return subprocess.CompletedProcess(args, 0, service_rows, "")
            if "smoke_check.py" in cmd or "model_smoke_check.py" in cmd:
                return subprocess.CompletedProcess(args, 0, "RESULT: ALL CHECKS PASSED", "")
            return subprocess.CompletedProcess(args, 0, "PASSED", "")

        monkeypatch.setattr(module, "_run", fake_run)
        monkeypatch.setattr(module, "_http_json", lambda api_base, path, timeout=10: (True, '{"status": "ok", "ready": true}'))
        monkeypatch.setattr(module, "_http_status", lambda url, timeout=10: (True, "status=200"))
        monkeypatch.setattr(module, "resolve_git", lambda: "git")

        assert module.main(["--run-model-smoke"]) == 0
        assert any("model_smoke_check.py" in cmd for cmd in commands)
