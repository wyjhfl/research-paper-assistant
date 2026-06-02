from __future__ import annotations

import json
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BF_YML = PROJECT_ROOT / ".github" / "workflows" / "backup-freshness.yml"
FRESHNESS_SCRIPT = PROJECT_ROOT / "scripts" / "check_backup_freshness.py"


def _load_bf():
    data = yaml.safe_load(BF_YML.read_text(encoding="utf-8"))
    trigger_key = True if True in data else "on"
    data["on"] = data[trigger_key]
    return data


class TestBackupFreshnessWorkflowExists:
    def test_workflow_file_exists(self):
        assert BF_YML.exists(), ".github/workflows/backup-freshness.yml not found"


class TestBackupFreshnessTriggers:
    def test_has_workflow_dispatch(self):
        bf = _load_bf()
        assert "workflow_dispatch" in bf["on"], "workflow_dispatch trigger missing"

    def test_has_schedule(self):
        bf = _load_bf()
        assert "schedule" in bf["on"], "schedule trigger missing"

    def test_schedule_cron_present(self):
        bf = _load_bf()
        schedules = bf["on"]["schedule"]
        assert len(schedules) >= 1, "at least one schedule entry required"
        assert "cron" in schedules[0], "schedule must have cron expression"


class TestBackupFreshnessInputs:
    def test_max_age_hours_input(self):
        bf = _load_bf()
        inputs = bf["on"]["workflow_dispatch"].get("inputs", {})
        assert "max_age_hours" in inputs, "max_age_hours input missing"

    def test_backups_dir_input(self):
        bf = _load_bf()
        inputs = bf["on"]["workflow_dispatch"].get("inputs", {})
        assert "backups_dir" in inputs, "backups_dir input missing"

    def test_allow_missing_manifest_input(self):
        bf = _load_bf()
        inputs = bf["on"]["workflow_dispatch"].get("inputs", {})
        assert "allow_missing_manifest" in inputs, "allow_missing_manifest input missing"


class TestBackupFreshnessScript:
    def test_uses_check_backup_freshness(self):
        content = BF_YML.read_text(encoding="utf-8")
        assert "check_backup_freshness.py" in content, "must use check_backup_freshness.py"

    def test_uses_max_age_hours_arg(self):
        content = BF_YML.read_text(encoding="utf-8")
        assert "--max-age-hours" in content, "must pass --max-age-hours"

    def test_uses_backups_dir_arg(self):
        content = BF_YML.read_text(encoding="utf-8")
        assert "--backups-dir" in content, "must pass --backups-dir"


class TestBackupFreshnessSecurity:
    def test_no_confirm_restore(self):
        content = BF_YML.read_text(encoding="utf-8")
        assert "ConfirmRestore" not in content, "must not contain ConfirmRestore"

    def test_no_restore_all(self):
        content = BF_YML.read_text(encoding="utf-8")
        assert "restore_all" not in content, "must not contain restore_all"

    def test_no_backup_all(self):
        content = BF_YML.read_text(encoding="utf-8")
        assert "backup_all" not in content, "must not contain backup_all"

    def test_no_secrets(self):
        content = BF_YML.read_text(encoding="utf-8")
        for pattern in ["sk-", "tp-", "API_KEY=", "SECRET=", "PASSWORD=", "Authorization"]:
            assert pattern not in content, f"Potential secret found: {pattern}"

    def test_no_upload_artifact_of_backups(self):
        bf = _load_bf()
        for job_name, job in bf["jobs"].items():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if "upload-artifact" in uses:
                    with_val = step.get("with", {}).get("path", "")
                    assert "artifacts/backups" not in with_val, f"{job_name}: must not upload backups"
                    assert "artifacts/evals" not in with_val, f"{job_name}: must not upload evals"
                    assert ".env" not in with_val, f"{job_name}: must not upload .env"

    def test_permissions_minimal(self):
        bf = _load_bf()
        perms = bf.get("permissions", {})
        assert perms.get("contents") == "read" or perms == {"contents": "read"}, \
            f"permissions must be contents: read only, got: {perms}"
        assert "write" not in str(perms), "no write permissions allowed"


class TestBackupFreshnessRunnerNote:
    def test_mentions_self_hosted_or_runner_requirement(self):
        content = BF_YML.read_text(encoding="utf-8")
        has_note = any(kw in content.lower() for kw in ["self-hosted", "hosted runner", "runner", "backups_dir"])
        assert has_note, "workflow must note that hosted runners cannot access production backups"

    def test_schedule_has_enable_gate(self):
        content = BF_YML.read_text(encoding="utf-8")
        assert "BACKUP_FRESHNESS_ENABLED" in content, "schedule job must check BACKUP_FRESHNESS_ENABLED variable"

    def test_workflow_dispatch_not_blocked_by_enable_gate(self):
        bf = _load_bf()
        job = bf["jobs"]["check-freshness"]
        if_condition = job.get("if", "")
        assert "workflow_dispatch" in if_condition or "event_name" in if_condition, \
            "if condition should allow workflow_dispatch to bypass BACKUP_FRESHNESS_ENABLED"

    def test_mentions_enable_variable_in_note(self):
        content = BF_YML.read_text(encoding="utf-8")
        assert "BACKUP_FRESHNESS_ENABLED" in content, "workflow must mention BACKUP_FRESHNESS_ENABLED in documentation/note"


class TestCheckBackupFreshnessScript:
    def test_script_exists(self):
        assert FRESHNESS_SCRIPT.exists(), "scripts/check_backup_freshness.py not found"

    def test_latest_manifest_is_filename_only(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert 'latest["name"]' in content or "latest['name']" in content, "latest_manifest must use name field (filename only)"

    def test_no_absolute_path_in_output(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "str(latest)" not in content, "must not output full path of manifest"
        assert "str(latest.resolve())" not in content, "must not output resolved path of manifest"
        assert 'latest["name"]' in content or "latest['name']" in content, "must use name field not path"

    def test_has_allow_missing_manifest_arg(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "--allow-missing-manifest" in content, "must support --allow-missing-manifest"

    def test_has_max_age_hours_arg(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "--max-age-hours" in content, "must support --max-age-hours"

    def test_has_backups_dir_arg(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "--backups-dir" in content, "must support --backups-dir"

    def test_has_checked_manifest_count(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "checked_manifest_count" in content, "must output checked_manifest_count"

    def test_has_skipped_manifest_count(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "skipped_manifest_count" in content, "must output skipped_manifest_count"

    def test_has_timestamp_source(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "timestamp_source" in content, "must output timestamp_source"

    def test_selects_by_timestamp_not_mtime(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "timestamp_dt" in content, "must select latest by parsed timestamp_dt"
        assert 'key=lambda c: c["timestamp_dt"]' in content, "must use max() by timestamp_dt"

    def test_handles_invalid_json_gracefully(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "Skipped invalid manifest" in content, "must warn about skipped invalid manifests"

    def test_uses_try_parse_timestamp(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "_try_parse_timestamp" in content, "must use _try_parse_timestamp for clean source detection"

    def test_invalid_timestamp_uses_mtime_fallback(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "mtime_fallback" in content, "must mark invalid timestamp as mtime_fallback"
        assert "fallback_reason" in content, "must record fallback_reason for invalid/missing timestamp"

    def test_warns_about_fallback_with_filename(self):
        content = FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        assert "mtime fallback" in content, "must warn when mtime fallback is used"
