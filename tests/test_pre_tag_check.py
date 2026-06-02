from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRE_TAG_SCRIPT = PROJECT_ROOT / "scripts" / "pre_tag_check.py"
GITIGNORE = PROJECT_ROOT / ".gitignore"


class TestPreTagCheckScriptExists:
    def test_script_exists(self):
        assert PRE_TAG_SCRIPT.exists(), "scripts/pre_tag_check.py not found"


class TestPreTagCheckSafety:
    def test_no_confirm_restore_execution(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "subprocess" not in content or "ConfirmRestore" not in [l.strip() for l in content.splitlines() if "subprocess" in l], "must not execute ConfirmRestore"
        lines_with_confirm = [l for l in content.splitlines() if "ConfirmRestore" in l and "in content" not in l and '"' not in l.split("ConfirmRestore")[0][-5:]]
        assert len(lines_with_confirm) == 0, "must not execute ConfirmRestore"

    def test_no_restore_all_execution(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        lines_with_restore = [l for l in content.splitlines() if "restore_all" in l and "in content" not in l]
        assert len(lines_with_restore) == 0, "must not execute restore_all"

    def test_no_cleanup_confirm_execution(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        lines_with_confirm = [l for l in content.splitlines() if "--confirm" in l and "in content" not in l]
        assert len(lines_with_confirm) == 0, "must not execute --confirm"

    def test_no_eval_real_model_execution(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        lines_with_eval = [l for l in content.splitlines() if "eval_real_model" in l and "in content" not in l and "append" not in l]
        assert len(lines_with_eval) == 0, "must not execute eval_real_model"

    def test_no_docker_compose_up(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "docker compose up" not in content, "must not contain docker compose up"
        assert "docker-compose up" not in content, "must not contain docker-compose up"

    def test_no_tag_create(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "git tag" not in content, "must not create git tags"

    def test_no_push(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "git push" not in content, "must not push"

    def test_no_backup_all(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "backup_all" not in content, "must not run backup_all"


class TestPreTagCheckNoSecrets:
    def test_no_sk_prefix_in_logic(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        code_lines = [l for l in lines if "compile" not in l and "_FORBIDDEN" not in l]
        code_text = "\n".join(code_lines)
        assert "sk-" not in code_text, "must not contain sk- prefix in logic"

    def test_no_tp_prefix_in_logic(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        code_lines = [l for l in lines if "compile" not in l and "_FORBIDDEN" not in l]
        code_text = "\n".join(code_lines)
        assert "tp-" not in code_text, "must not contain tp- prefix in logic"


class TestPreTagCheckStructure:
    def test_has_checks_array(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert '"checks"' in content, "must output checks array"

    def test_has_warnings_array(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert '"warnings"' in content, "must output warnings array"

    def test_has_ok_field(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert '"ok"' in content, "must output ok field"

    def test_has_sanitize(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "_sanitize" in content, "must have _sanitize function"

    def test_has_make_path_relative(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "_make_path_relative" in content, "must have _make_path_relative"


class TestPreTagCheckChecks:
    def test_has_release_notes_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "RELEASE_NOTES" in content, "must check release notes existence"

    def test_has_collect_evidence_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "collect_rc_evidence" in content, "must check collect_rc_evidence.py existence"

    def test_has_gitignore_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "artifacts/rc/" in content, "must check artifacts/rc/ gitignored"

    def test_has_env_tracking_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "ls-files" in content, "must check .env not tracked by git"

    def test_has_docs_secrets_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "check_docs_secrets" in content, "must check docs secrets scan"

    def test_has_mojibake_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "check_frontend_mojibake" in content, "must check frontend mojibake scan"

    def test_has_backup_freshness_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "BACKUP_FRESHNESS_ENABLED" in content, "must check backup freshness enable gate"

    def test_has_ci_safety_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "ci.yml" in content, "must check ci.yml safety"

    def test_has_version_consistency_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "version_consistency" in content, "must check version consistency"

    def test_has_git_unavailable_handling(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "git unavailable" in content, "must handle git unavailable"

    def test_git_unavailable_env_not_tracked_fails(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        in_env_check = False
        for line in lines:
            if "_check_env_not_tracked" in line and "def" in line:
                in_env_check = True
            if in_env_check and "git unavailable" in line:
                assert "ok=False" in line or 'ok": False' in line, "git unavailable must return ok=False"
                break


class TestPreTagCheckSmoke:
    def test_smoke_run_json_parseable(self):
        if not PRE_TAG_SCRIPT.exists():
            return
        result = subprocess.run(
            [sys.executable, str(PRE_TAG_SCRIPT)],
            capture_output=True, text=True, timeout=120,
        )
        data = json.loads(result.stdout)
        assert "ok" in data, "must have ok field"
        assert "checks" in data, "must have checks field"
        assert "warnings" in data, "must have warnings field"
        assert isinstance(data["checks"], list), "checks must be a list"
        assert len(data["checks"]) == 9, f"expected 9 checks, got {len(data['checks'])}"

    def test_output_no_absolute_paths(self):
        if not PRE_TAG_SCRIPT.exists():
            return
        result = subprocess.run(
            [sys.executable, str(PRE_TAG_SCRIPT)],
            capture_output=True, text=True, timeout=120,
        )
        assert str(PROJECT_ROOT) not in result.stdout, "must not contain absolute paths"

    def test_output_no_secrets(self):
        if not PRE_TAG_SCRIPT.exists():
            return
        result = subprocess.run(
            [sys.executable, str(PRE_TAG_SCRIPT)],
            capture_output=True, text=True, timeout=120,
        )
        for pattern in ["sk-", "tp-", "API_KEY=", "SECRET=", "PASSWORD=", "DATABASE_URL="]:
            assert pattern not in result.stdout, f"must not contain {pattern}"


class TestReleaseNotes:
    def test_release_notes_exist(self):
        rn = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.1-rc.1.md"
        assert rn.exists(), "RELEASE_NOTES_v1.0.1-rc.1.md must exist"

    def test_no_secrets_in_release_notes(self):
        rn = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.1-rc.1.md"
        if not rn.exists():
            return
        content = rn.read_text(encoding="utf-8")
        for pattern in ["API_KEY=", "SECRET=", "PASSWORD=", "DATABASE_URL="]:
            assert pattern not in content, f"release notes must not contain {pattern}"

    def test_no_all_checks_passed(self):
        rn = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.1-rc.1.md"
        if not rn.exists():
            return
        content = rn.read_text(encoding="utf-8")
        assert "ALL CHECKS PASSED" not in content, "must not claim ALL CHECKS PASSED without full gate"

    def test_contains_phase_summaries(self):
        rn = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.1-rc.1.md"
        if not rn.exists():
            return
        content = rn.read_text(encoding="utf-8")
        for phase in ["Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5"]:
            assert phase in content, f"must contain {phase} summary"

    def test_contains_unexecuted_items(self):
        rn = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.1-rc.1.md"
        if not rn.exists():
            return
        content = rn.read_text(encoding="utf-8")
        assert "Docker" in content or "docker" in content, "must mention Docker as unexecuted"
        assert "Playwright" in content or "E2E" in content, "must mention E2E as unexecuted"


class TestVersionConsistency:
    def test_config_py_version(self):
        config_py = PROJECT_ROOT / "apps" / "api" / "app" / "config.py"
        content = config_py.read_text(encoding="utf-8")
        assert "1.0.1-rc.1" in content, "config.py must have version 1.0.1-rc.1"

    def test_env_example_version(self):
        env_example = PROJECT_ROOT / ".env.example"
        content = env_example.read_text(encoding="utf-8")
        assert "APP_VERSION=1.0.1-rc.1" in content, ".env.example must have APP_VERSION=1.0.1-rc.1"

    def test_api_contract_version(self):
        api_contract = PROJECT_ROOT / "docs" / "API_CONTRACT.md"
        content = api_contract.read_text(encoding="utf-8")
        assert "1.0.1-rc.1" in content, "API_CONTRACT.md must have version 1.0.1-rc.1"


class TestPreTagCheckCrossCwd:
    def test_pre_tag_check_from_temp_cwd(self):
        if not PRE_TAG_SCRIPT.exists():
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, str(PRE_TAG_SCRIPT.resolve())],
                capture_output=True, text=True, timeout=120,
                cwd=tmpdir,
            )
            data = json.loads(result.stdout)
            assert "ok" in data
            assert "checks" in data
            assert str(PROJECT_ROOT) not in result.stdout, "must not contain absolute paths"


class TestCollectEvidenceCrossCwd:
    def test_collect_evidence_from_temp_cwd(self):
        rc_script = PROJECT_ROOT / "scripts" / "collect_rc_evidence.py"
        if not rc_script.exists():
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "rc_output"
            result = subprocess.run(
                [sys.executable, str(rc_script.resolve()), "--output-dir", str(out_dir)],
                capture_output=True, text=True, timeout=60,
                cwd=tempfile.gettempdir(),
            )
            json_files = list(out_dir.glob("rc_evidence_*.json"))
            assert len(json_files) >= 1, "must generate JSON even from different cwd"
            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            assert "git" in data
            assert "version" in data
            json_content = json_files[0].read_text(encoding="utf-8")
            assert str(PROJECT_ROOT) not in json_content, "must not contain absolute paths"


class TestBackupLifecycleNoBareReadText:
    def test_no_bare_read_text(self):
        test_file = PROJECT_ROOT / "apps" / "api" / "tests" / "test_backup_lifecycle.py"
        if not test_file.exists():
            return
        content = test_file.read_text(encoding="utf-8")
        import re
        bare_matches = re.findall(r'\.read_text\(\)', content)
        assert len(bare_matches) == 0, f"Found {len(bare_matches)} bare .read_text() calls, must use .read_text(encoding='utf-8')"


class TestResolveGit:
    def test_resolve_git_exists_in_pre_tag_check(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "resolve_git" in content, "pre_tag_check.py must have resolve_git function"

    def test_resolve_git_exists_in_collect_rc_evidence(self):
        rc_script = PROJECT_ROOT / "scripts" / "collect_rc_evidence.py"
        content = rc_script.read_text(encoding="utf-8")
        assert "resolve_git" in content, "collect_rc_evidence.py must have resolve_git function"

    def test_resolve_git_uses_shutil_which(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "shutil.which" in content, "resolve_git must try shutil.which first"

    def test_resolve_git_uses_winreg_fallback(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "winreg" in content, "resolve_git must have winreg fallback for Windows"
        assert "GitForWindows" in content, "resolve_git must read GitForWindows registry key"

    def test_resolve_git_uses_common_paths_fallback(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "ProgramFiles" in content, "resolve_git must check ProgramFiles common paths"

    def test_resolve_git_uses_path_scan_fallback(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        assert "git/cmd" in content, "resolve_git must scan PATH for git/cmd entries"

    def test_resolve_git_returns_string(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pre_tag_check", str(PRE_TAG_SCRIPT))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.resolve_git()
        assert isinstance(result, str), "resolve_git must return a string"
        assert len(result) > 0, "resolve_git must return non-empty string"

    def test_resolve_git_result_is_executable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pre_tag_check", str(PRE_TAG_SCRIPT))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        git_exe = mod.resolve_git()
        result = subprocess.run([git_exe, "--version"], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, f"resolve_git result must be executable, got: {git_exe}"
        assert "git version" in result.stdout.lower(), f"resolve_git result must be git, got: {result.stdout}"

    def test_resolve_git_caches_result(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pre_tag_check", str(PRE_TAG_SCRIPT))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod._RESOLVED_GIT = None
        r1 = mod.resolve_git()
        r2 = mod.resolve_git()
        assert r1 == r2, "resolve_git must cache result"

    def test_env_not_tracked_uses_resolve_git(self):
        content = PRE_TAG_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()
        in_env_check = False
        found_resolve_git_call = False
        for line in lines:
            if "_check_env_not_tracked" in line and "def" in line:
                in_env_check = True
            if in_env_check:
                if "resolve_git" in line:
                    found_resolve_git_call = True
                if "def " in line and "_check_env_not_tracked" not in line:
                    break
        assert found_resolve_git_call, "_check_env_not_tracked must use resolve_git()"

    def test_collect_evidence_git_info_uses_resolve_git(self):
        rc_script = PROJECT_ROOT / "scripts" / "collect_rc_evidence.py"
        content = rc_script.read_text(encoding="utf-8")
        lines = content.splitlines()
        in_git_info = False
        found_resolve_git_call = False
        for line in lines:
            if "_get_git_info" in line and "def" in line:
                in_git_info = True
            if in_git_info:
                if "resolve_git" in line:
                    found_resolve_git_call = True
                if "def " in line and "_get_git_info" not in line:
                    break
        assert found_resolve_git_call, "_get_git_info must use resolve_git()"
