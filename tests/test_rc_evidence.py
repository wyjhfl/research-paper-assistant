from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RC_SCRIPT = PROJECT_ROOT / "scripts" / "collect_rc_evidence.py"
GITIGNORE = PROJECT_ROOT / ".gitignore"


class TestRCEvidenceScriptExists:
    def test_script_exists(self):
        assert RC_SCRIPT.exists(), "scripts/collect_rc_evidence.py not found"


class TestRCEvidenceSafety:
    def test_no_confirm_restore(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "ConfirmRestore" not in content, "must not contain ConfirmRestore"

    def test_no_restore_all(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "restore_all" not in content, "must not contain restore_all"

    def test_no_cleanup_confirm(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "--confirm" not in content, "must not contain --confirm"

    def test_no_eval_real_model(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "eval_real_model" not in content, "must not contain eval_real_model"

    def test_no_docker_compose_up(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "docker compose up" not in content, "must not contain docker compose up"
        assert "docker-compose up" not in content, "must not contain docker-compose up"


class TestRCEvidenceNoSecrets:
    def test_no_sk_prefix(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        code_lines = [l for l in lines if not l.strip().startswith("#") and "compile" not in l and "_FORBIDDEN" not in l]
        code_text = "\n".join(code_lines)
        assert "sk-" not in code_text, "must not contain sk- prefix in logic"

    def test_no_tp_prefix(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        code_lines = [l for l in lines if not l.strip().startswith("#") and "compile" not in l and "_FORBIDDEN" not in l]
        code_text = "\n".join(code_lines)
        assert "tp-" not in code_text, "must not contain tp- prefix in logic"

    def test_no_api_key_assignment(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        code_lines = [l for l in lines if not l.strip().startswith("#") and "compile" not in l and "_FORBIDDEN" not in l]
        code_text = "\n".join(code_lines)
        assert "API_KEY=" not in code_text, "must not contain API_KEY= in logic"

    def test_no_secret_assignment(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        code_lines = [l for l in lines if not l.strip().startswith("#") and "compile" not in l and "_FORBIDDEN" not in l]
        code_text = "\n".join(code_lines)
        assert "SECRET=" not in code_text, "must not contain SECRET= in logic"

    def test_no_password_assignment(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        code_lines = [l for l in lines if not l.strip().startswith("#") and "compile" not in l and "_FORBIDDEN" not in l]
        code_text = "\n".join(code_lines)
        assert "PASSWORD=" not in code_text, "must not contain PASSWORD= in logic"

    def test_has_sanitize_for_authorization(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "_sanitize" in content, "must have _sanitize function"
        assert "Authorization" in content, "must sanitize Authorization in _FORBIDDEN_PATTERNS"

    def test_has_sanitize_for_database_url(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "_sanitize" in content, "must have _sanitize function"
        assert "DATABASE_URL" in content, "must sanitize DATABASE_URL in _FORBIDDEN_PATTERNS"


class TestRCEvidenceOutputConstraints:
    def test_no_absolute_paths_in_output(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "_make_path_relative" in content, "must sanitize absolute paths in output"

    def test_no_upload_backup_artifacts(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "artifacts/backups" not in content or "no_backup_artifacts" in content, \
            "must not upload backup artifacts content"

    def test_no_upload_eval_artifacts(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "artifacts/evals" not in content or "no_eval_artifacts" in content, \
            "must not upload eval artifacts content"

    def test_output_dir_is_artifacts_rc(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "artifacts/rc" in content, "default output must be artifacts/rc"


class TestRCEvidenceGitignore:
    def test_artifacts_rc_in_gitignore(self):
        content = GITIGNORE.read_text(encoding="utf-8")
        assert "artifacts/rc/" in content, "artifacts/rc/ must be in .gitignore"


class TestRCEvidenceGitUnavailable:
    def test_git_unavailable_does_not_crash(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "unavailable" in content, "must handle git unavailable gracefully"

    def test_git_commands_use_cwd(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "cwd=str(project_root)" in content, "git commands must use cwd=project_root"

    def test_scanner_commands_use_cwd(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        scanner_lines = [l for l in content.splitlines() if "_run_scanner" in l or "_run_safe" in l and "scanner" in l.lower()]
        assert "cwd=str(project_root)" in content, "scanner commands must use cwd=project_root"


class TestRCEvidenceVersionRead:
    def test_reads_config_py_first(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "config.py" in content, "must read version from config.py"
        assert "APP_VERSION" in content, "must read APP_VERSION from config.py"

    def test_evidence_json_has_version(self):
        if not RC_SCRIPT.exists():
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [sys.executable, str(RC_SCRIPT), "--output-dir", tmpdir],
                capture_output=True, text=True, timeout=60,
            )
            output_dir = Path(tmpdir)
            json_files = list(output_dir.glob("rc_evidence_*.json"))
            if json_files:
                data = json.loads(json_files[0].read_text(encoding="utf-8"))
                version = data.get("version", {}).get("app_version", "unknown")
                assert version != "unknown", "app_version should not be unknown when config.py exists"
                assert version == "1.0.1-rc.1", f"app_version should be 1.0.1-rc.1, got {version}"


class TestRCEvidenceCwdConsistency:
    def test_run_from_different_dir(self):
        if not RC_SCRIPT.exists():
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            result = subprocess.run(
                [sys.executable, str(RC_SCRIPT.resolve()), "--output-dir", str(out_dir)],
                capture_output=True, text=True, timeout=60,
                cwd=tempfile.gettempdir(),
            )
            json_files = list(out_dir.glob("rc_evidence_*.json"))
            assert len(json_files) >= 1, "must generate JSON even when run from different cwd"
            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            assert "git" in data
            assert "version" in data

    def test_git_unavailable_does_not_crash_evidence(self):
        content = RC_SCRIPT.read_text(encoding="utf-8")
        assert "unavailable" in content, "must handle git unavailable gracefully in evidence"
        assert "exit_code" in content, "must check exit_code from git commands"


class TestRCEvidenceSmoke:
    def test_smoke_run_generates_json_and_md(self):
        if not RC_SCRIPT.exists():
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, str(RC_SCRIPT), "--output-dir", tmpdir],
                capture_output=True, text=True, timeout=60,
            )
            output_dir = Path(tmpdir)
            json_files = list(output_dir.glob("rc_evidence_*.json"))
            md_files = list(output_dir.glob("rc_evidence_*.md"))
            assert len(json_files) >= 1, "must generate at least one JSON file"
            assert len(md_files) >= 1, "must generate at least one MD file"

            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            assert "timestamp" in data, "JSON must contain timestamp"
            assert "git" in data, "JSON must contain git info"
            assert "scanners" in data, "JSON must contain scanners"
            assert "workflows" in data, "JSON must contain workflows"

    def test_json_output_no_absolute_paths(self):
        if not RC_SCRIPT.exists():
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [sys.executable, str(RC_SCRIPT), "--output-dir", tmpdir],
                capture_output=True, text=True, timeout=60,
            )
            output_dir = Path(tmpdir)
            json_files = list(output_dir.glob("rc_evidence_*.json"))
            if json_files:
                content = json_files[0].read_text(encoding="utf-8")
                assert str(Path(tmpdir).parent) not in content, "JSON must not contain absolute paths"

    def test_json_output_no_secrets(self):
        if not RC_SCRIPT.exists():
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [sys.executable, str(RC_SCRIPT), "--output-dir", tmpdir],
                capture_output=True, text=True, timeout=60,
            )
            output_dir = Path(tmpdir)
            json_files = list(output_dir.glob("rc_evidence_*.json"))
            if json_files:
                content = json_files[0].read_text(encoding="utf-8")
                for pattern in ["sk-", "tp-", "API_KEY=", "SECRET=", "PASSWORD=", "Authorization", "DATABASE_URL="]:
                    assert pattern not in content, f"JSON must not contain {pattern}"
