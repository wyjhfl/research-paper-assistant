from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PY = PROJECT_ROOT / "apps" / "api" / "app" / "config.py"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
API_CONTRACT = PROJECT_ROOT / "docs" / "API_CONTRACT.md"
RELEASE_NOTES = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.1-rc.1.md"
BACKLOG = PROJECT_ROOT / "docs" / "V1_0_1_BACKLOG.md"
GITIGNORE = PROJECT_ROOT / ".gitignore"
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
BF_YML = PROJECT_ROOT / ".github" / "workflows" / "backup-freshness.yml"
TEST_BACKUP_LIFECYCLE = PROJECT_ROOT / "apps" / "api" / "tests" / "test_backup_lifecycle.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class TestVersionConsistency:
    def test_config_py_version(self):
        content = _read(CONFIG_PY)
        assert "1.0.1-rc.1" in content, "config.py must have 1.0.1-rc.1"

    def test_env_example_version(self):
        content = _read(ENV_EXAMPLE)
        assert "APP_VERSION=1.0.1-rc.1" in content, ".env.example must have APP_VERSION=1.0.1-rc.1"

    def test_api_contract_version(self):
        content = _read(API_CONTRACT)
        assert "1.0.1-rc.1" in content, "API_CONTRACT.md must have 1.0.1-rc.1"

    def test_release_notes_version(self):
        content = _read(RELEASE_NOTES)
        assert "1.0.1-rc.1" in content, "RELEASE_NOTES must mention 1.0.1-rc.1"

    def test_no_released_1_0_1_claim(self):
        for doc in [RELEASE_NOTES, BACKLOG]:
            if not doc.exists():
                continue
            content = _read(doc)
            assert "已发布 1.0.1" not in content, f"{doc.name} must not claim 1.0.1 is released"
            assert "released 1.0.1" not in content.lower(), f"{doc.name} must not claim 1.0.1 is released"


class TestReleaseNotesContent:
    def test_release_notes_exists(self):
        assert RELEASE_NOTES.exists(), "RELEASE_NOTES_v1.0.1-rc.1.md must exist"

    def test_no_all_checks_passed(self):
        content = _read(RELEASE_NOTES)
        assert "ALL CHECKS PASSED" not in content, "must not claim ALL CHECKS PASSED"

    def test_no_false_ci_claims(self):
        content = _read(RELEASE_NOTES)
        for claim in ["Docker 已通过", "Playwright 已通过", "GitHub Actions 已通过", "verify_all 已通过", "rc_gate 已通过", "真实模型 eval 已通过"]:
            assert claim not in content, f"must not claim {claim} without actual execution"

    def test_contains_phase_summaries(self):
        content = _read(RELEASE_NOTES)
        for phase in ["Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5"]:
            assert phase in content, f"must contain {phase} summary"

    def test_contains_unexecuted_items(self):
        content = _read(RELEASE_NOTES)
        assert "Docker" in content or "docker" in content, "must mention Docker as unexecuted or limitation"

    def test_no_secrets(self):
        content = _read(RELEASE_NOTES)
        for pattern in ["API_KEY=", "SECRET=", "PASSWORD=", "DATABASE_URL="]:
            assert pattern not in content, f"must not contain {pattern}"


class TestBacklogNumbering:
    def test_no_error_numbering_pattern(self):
        content = _read(BACKLOG)
        bad_patterns = re.findall(r"^\s+\d+\.\d+\.\s", content, re.MULTILINE)
        assert len(bad_patterns) == 0, f"Found error numbering patterns: {bad_patterns}"


class TestGitHygiene:
    def test_artifacts_rc_gitignored(self):
        content = _read(GITIGNORE)
        assert "artifacts/rc/" in content, "artifacts/rc/ must be in .gitignore"

    def test_artifacts_backups_gitignored(self):
        content = _read(GITIGNORE)
        assert "artifacts/backups/" in content, "artifacts/backups/ must be in .gitignore"

    def test_artifacts_evals_gitignored(self):
        content = _read(GITIGNORE)
        assert "artifacts/evals/" in content, "artifacts/evals/ must be in .gitignore"


class TestWorkflowSafety:
    def test_backup_freshness_has_enable_gate(self):
        content = _read(BF_YML)
        assert "BACKUP_FRESHNESS_ENABLED" in content, "backup-freshness.yml must have BACKUP_FRESHNESS_ENABLED gate"

    def test_ci_no_confirm_restore(self):
        content = _read(CI_YML)
        assert "ConfirmRestore" not in content, "ci.yml must not contain ConfirmRestore"

    def test_ci_no_eval_real_model(self):
        content = _read(CI_YML)
        assert "eval_real_model" not in content, "ci.yml must not contain eval_real_model"

    def test_ci_no_upload_artifacts_backups(self):
        content = _read(CI_YML)
        assert "artifacts/backups" not in content, "ci.yml must not reference artifacts/backups"


class TestTestFileEncoding:
    def test_no_bare_read_text(self):
        content = _read(TEST_BACKUP_LIFECYCLE)
        bare_matches = re.findall(r"\.read_text\(\)", content)
        assert len(bare_matches) == 0, f"Found {len(bare_matches)} bare .read_text() calls"


class TestDocsNoGeneratedArtifacts:
    def test_docs_no_rc_evidence_json(self):
        docs_dir = PROJECT_ROOT / "docs"
        rc_jsons = list(docs_dir.glob("rc_evidence_*.json"))
        assert len(rc_jsons) == 0, f"docs/ should not contain RC evidence JSON: {[f.name for f in rc_jsons]}"

    def test_docs_no_pre_tag_check_json(self):
        docs_dir = PROJECT_ROOT / "docs"
        pt_jsons = list(docs_dir.glob("pre_tag_check_*.json"))
        assert len(pt_jsons) == 0, f"docs/ should not contain pre-tag check JSON: {[f.name for f in pt_jsons]}"
