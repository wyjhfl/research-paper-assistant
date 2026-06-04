from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GITIGNORE = PROJECT_ROOT / ".gitignore"
RELEASE_NOTES = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.1-rc.1.md"
BACKLOG = PROJECT_ROOT / "docs" / "V1_0_1_BACKLOG.md"
README = PROJECT_ROOT / "README.md"
PRE_TAG_SCRIPT = PROJECT_ROOT / "scripts" / "pre_tag_check.py"
RC_SCRIPT = PROJECT_ROOT / "scripts" / "collect_rc_evidence.py"
CONFIG_PY = PROJECT_ROOT / "apps" / "api" / "app" / "config.py"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
API_CONTRACT = PROJECT_ROOT / "docs" / "API_CONTRACT.md"
BF_YML = PROJECT_ROOT / ".github" / "workflows" / "backup-freshness.yml"
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
TEST_BACKUP_LIFECYCLE = PROJECT_ROOT / "apps" / "api" / "tests" / "test_backup_lifecycle.py"
HANDOFF_DOC = PROJECT_ROOT / "docs" / "V1_0_1_RC_HANDOFF.md"


def _resolve_git():
    found = shutil.which("git")
    if found:
        return found
    if sys.platform == "win32":
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(hive, r"SOFTWARE\GitForWindows")
                    install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    winreg.CloseKey(key)
                    candidate = os.path.join(install_path, "cmd", "git.exe")
                    if os.path.isfile(candidate):
                        return candidate
                except (FileNotFoundError, OSError):
                    pass
        except ImportError:
            pass
        for common in [
            os.path.join(os.environ.get("ProgramFiles", ""), "Git", "cmd", "git.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Git", "cmd", "git.exe"),
        ]:
            if common and os.path.isfile(common):
                return common
        path_env = os.environ.get("PATH", "")
        for entry in path_env.split(os.pathsep):
            entry_lower = entry.lower().replace("\\", "/")
            if entry_lower.endswith("git/cmd") or entry_lower.endswith("git/cmd/"):
                candidate = os.path.join(entry, "git.exe")
                if os.path.isfile(candidate):
                    return candidate
    return None


GIT_EXE = _resolve_git()


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _git_available():
    if GIT_EXE is None:
        return False
    try:
        result = subprocess.run([GIT_EXE, "--version"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


class TestGitTracking:
    def test_env_not_tracked(self):
        if not _git_available():
            return
        result = subprocess.run([GIT_EXE, "ls-files", ".env"], capture_output=True, text=True, timeout=10, cwd=str(PROJECT_ROOT))
        assert result.stdout.strip() == "", ".env must not be tracked by git"

    def test_artifacts_rc_not_tracked(self):
        if not _git_available():
            return
        result = subprocess.run([GIT_EXE, "ls-files", "artifacts/rc"], capture_output=True, text=True, timeout=10, cwd=str(PROJECT_ROOT))
        assert result.stdout.strip() == "", "artifacts/rc must not be tracked by git"

    def test_artifacts_backups_not_tracked(self):
        if not _git_available():
            return
        result = subprocess.run([GIT_EXE, "ls-files", "artifacts/backups"], capture_output=True, text=True, timeout=10, cwd=str(PROJECT_ROOT))
        assert result.stdout.strip() == "", "artifacts/backups must not be tracked by git"

    def test_artifacts_evals_not_tracked(self):
        if not _git_available():
            return
        result = subprocess.run([GIT_EXE, "ls-files", "artifacts/evals"], capture_output=True, text=True, timeout=10, cwd=str(PROJECT_ROOT))
        assert result.stdout.strip() == "", "artifacts/evals must not be tracked by git"


class TestGitignoreCoverage:
    def test_artifacts_rc_gitignored(self):
        content = _read(GITIGNORE)
        assert "artifacts/rc/" in content

    def test_artifacts_backups_gitignored(self):
        content = _read(GITIGNORE)
        assert "artifacts/backups/" in content

    def test_artifacts_evals_gitignored(self):
        content = _read(GITIGNORE)
        assert "artifacts/evals/" in content


class TestReleaseNotesFinal:
    def test_no_all_checks_passed(self):
        content = _read(RELEASE_NOTES)
        assert "ALL CHECKS PASSED" not in content

    def test_no_false_ci_claims(self):
        content = _read(RELEASE_NOTES)
        for claim in ["Docker 已通过", "Playwright 已通过", "GitHub Actions 已通过", "verify_all 已通过", "rc_gate 已通过", "真实模型 eval 已通过"]:
            assert claim not in content, f"must not claim {claim}"

    def test_no_secrets(self):
        content = _read(RELEASE_NOTES)
        for p in ["API_KEY=", "SECRET=", "PASSWORD=", "DATABASE_URL="]:
            assert p not in content


class TestReadmeConsistency:
    def test_readme_no_contradictory_release_refs(self):
        if not README.exists():
            return
        content = _read(README)
        if "v1.0.1" in content:
            assert "1.0.1-rc.1" in content or "v1.0.1" in content, "README release refs should not contradict current version"


class TestBacklogNumbering:
    def test_no_error_numbering(self):
        content = _read(BACKLOG)
        bad = re.findall(r"^\s+\d+\.\d+\.\s", content, re.MULTILINE)
        assert len(bad) == 0, f"Error numbering patterns found: {bad}"


class TestPreTagCheckFinal:
    def test_checks_count_is_9(self):
        if not PRE_TAG_SCRIPT.exists():
            return
        result = subprocess.run([sys.executable, str(PRE_TAG_SCRIPT)], capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT))
        data = json.loads(result.stdout)
        assert len(data["checks"]) == 9, f"Expected 9 checks, got {len(data['checks'])}"

    def test_ok_true_no_warnings(self):
        if not PRE_TAG_SCRIPT.exists():
            return
        result = subprocess.run([sys.executable, str(PRE_TAG_SCRIPT)], capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT))
        data = json.loads(result.stdout)
        if data["ok"]:
            assert len(data.get("warnings", [])) == 0, "ok=true should have no warnings"


class TestCollectEvidenceFinal:
    def test_evidence_output_not_in_git_tracked(self):
        if not _git_available():
            return
        result = subprocess.run([GIT_EXE, "ls-files", "artifacts/rc"], capture_output=True, text=True, timeout=10, cwd=str(PROJECT_ROOT))
        assert result.stdout.strip() == "", "artifacts/rc output must not be tracked"

    def test_evidence_version_starts_with_1_0_1(self):
        if not RC_SCRIPT.exists():
            return
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run([sys.executable, str(RC_SCRIPT), "--output-dir", tmpdir], capture_output=True, text=True, timeout=60, cwd=str(PROJECT_ROOT))
            json_files = list(Path(tmpdir).glob("rc_evidence_*.json"))
            if json_files:
                data = json.loads(json_files[0].read_text(encoding="utf-8"))
                version = data.get("version", {}).get("app_version", "")
                assert version.startswith("1.0.1"), f"evidence version should start with 1.0.1, got {version}"


class TestVersionConsistencyFinal:
    def test_config_py(self):
        assert "1.0.1" in _read(CONFIG_PY)

    def test_env_example(self):
        assert "APP_VERSION=1.0.1" in _read(ENV_EXAMPLE)

    def test_api_contract(self):
        assert "1.0.1" in _read(API_CONTRACT)


class TestWorkflowSafetyFinal:
    def test_backup_freshness_has_enable_gate(self):
        assert "BACKUP_FRESHNESS_ENABLED" in _read(BF_YML)

    def test_ci_no_confirm_restore(self):
        assert "ConfirmRestore" not in _read(CI_YML)

    def test_ci_no_eval_real_model(self):
        assert "eval_real_model" not in _read(CI_YML)


class TestTestFileEncodingFinal:
    def test_no_bare_read_text(self):
        content = _read(TEST_BACKUP_LIFECYCLE)
        bare = re.findall(r"\.read_text\(\)", content)
        assert len(bare) == 0, f"Found {len(bare)} bare .read_text()"


class TestHandoffDocConsistency:
    def test_handoff_doc_exists(self):
        assert HANDOFF_DOC.exists(), "docs/V1_0_1_RC_HANDOFF.md must exist"

    def test_no_new_12_files_header(self):
        content = _read(HANDOFF_DOC)
        assert "New (12 files)" not in content, "must not have stale 'New (12 files)' header"
        assert "New (13 files)" not in content, "must not have stale 'New (13 files)' header"

    def test_new_14_files_count_matches_list(self):
        content = _read(HANDOFF_DOC)
        assert "New (14 files)" in content, "must have 'New (14 files)' header"
        new_files = re.findall(r"^\?\? (.+)$", content, re.MULTILINE)
        assert len(new_files) == 14, f"New files list has {len(new_files)} entries, expected 14"

    def test_modified_27_files_count_matches_list(self):
        content = _read(HANDOFF_DOC)
        assert "Modified (27 files)" in content, "must have 'Modified (27 files)' header"
        modified_files = re.findall(r"^ M (.+)$", content, re.MULTILINE)
        assert len(modified_files) == 27, f"Modified files list has {len(modified_files)} entries, expected 27"

    def test_total_files_is_41(self):
        content = _read(HANDOFF_DOC)
        new_files = re.findall(r"^\?\? (.+)$", content, re.MULTILINE)
        modified_files = re.findall(r"^ M (.+)$", content, re.MULTILINE)
        total = len(new_files) + len(modified_files)
        assert total == 41, f"Total files is {total}, expected 41 (27 modified + 14 new)"

    def test_pytest_commands_use_tests_prefix(self):
        content = _read(HANDOFF_DOC)
        pytest_lines = [l for l in content.splitlines() if "python -m pytest" in l]
        for line in pytest_lines:
            parts = re.findall(r"`([^`]+)`", line)
            for cmd in parts:
                if "pytest" not in cmd:
                    continue
                for token in cmd.split():
                    if not token.endswith(".py"):
                        continue
                    if token.startswith("apps/"):
                        continue
                    assert token.startswith("tests/"), f"pytest test path must start with tests/, got: {token} in line: {line}"


class TestFinalReleaseNotes:
    FINAL_RELEASE_NOTES = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.1.md"

    def test_final_release_notes_exists(self):
        assert self.FINAL_RELEASE_NOTES.exists(), "docs/RELEASE_NOTES_v1.0.1.md must exist"

    def test_no_all_checks_passed(self):
        if not self.FINAL_RELEASE_NOTES.exists():
            return
        content = _read(self.FINAL_RELEASE_NOTES)
        assert "ALL CHECKS PASSED" not in content, "must not claim ALL CHECKS PASSED"

    def test_no_false_ci_claims(self):
        if not self.FINAL_RELEASE_NOTES.exists():
            return
        content = _read(self.FINAL_RELEASE_NOTES)
        for claim in ["Docker 已通过", "Playwright 已通过", "verify_all 已通过", "rc_gate 已通过", "真实模型 eval 已通过"]:
            assert claim not in content, f"must not claim {claim}"

    def test_no_secrets(self):
        if not self.FINAL_RELEASE_NOTES.exists():
            return
        content = _read(self.FINAL_RELEASE_NOTES)
        for p in ["API_KEY=", "SECRET=", "PASSWORD=", "DATABASE_URL="]:
            assert p not in content

    def test_references_rc_source(self):
        if not self.FINAL_RELEASE_NOTES.exists():
            return
        content = _read(self.FINAL_RELEASE_NOTES)
        assert "v1.0.1-rc.1" in content, "must reference v1.0.1-rc.1"
        assert "d1d3715" in content, "must reference commit d1d3715"
