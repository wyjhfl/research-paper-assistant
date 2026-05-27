from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


def _get_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "docker-compose.yml").exists() or (current / ".env.example").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent.parent


def test_manifest_valid_ok():
    from scripts.validate_backup_manifest import validate_manifest

    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "db"
        storage_dir = Path(tmpdir) / "storage"
        db_dir.mkdir()
        storage_dir.mkdir()

        db_file = db_dir / "db_backup_20260101.sql"
        storage_file = storage_dir / "storage_backup_20260101.zip"
        db_file.write_text("dummy")
        storage_file.write_bytes(b"dummy")

        manifest = {
            "timestamp": "20260101_000000Z",
            "db_backup_file": "db_backup_20260101.sql",
            "storage_backup_file": "storage_backup_20260101.zip",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = Path(tmpdir) / "backup_manifest_20260101.json"
        manifest_path.write_text(json.dumps(manifest))

        result = validate_manifest(str(manifest_path))
        assert result["ok"] is True
        assert len(result["errors"]) == 0


def test_manifest_missing_db_backup_file():
    from scripts.validate_backup_manifest import validate_manifest

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest = {
            "timestamp": "20260101_000000Z",
            "db_backup_file": "",
            "storage_backup_file": "storage_backup_20260101.zip",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = Path(tmpdir) / "backup_manifest_20260101.json"
        manifest_path.write_text(json.dumps(manifest))

        result = validate_manifest(str(manifest_path))
        assert result["ok"] is False
        assert any("db_backup_file" in e for e in result["errors"])


def test_manifest_referenced_file_not_found():
    from scripts.validate_backup_manifest import validate_manifest

    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "db"
        storage_dir = Path(tmpdir) / "storage"
        db_dir.mkdir()
        storage_dir.mkdir()

        manifest = {
            "timestamp": "20260101_000000Z",
            "db_backup_file": "nonexistent.sql",
            "storage_backup_file": "nonexistent.zip",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = Path(tmpdir) / "backup_manifest_20260101.json"
        manifest_path.write_text(json.dumps(manifest))

        result = validate_manifest(str(manifest_path))
        assert result["ok"] is False
        assert any("not found" in e for e in result["errors"])


def test_manifest_contains_secret():
    from scripts.validate_backup_manifest import validate_manifest

    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "db"
        storage_dir = Path(tmpdir) / "storage"
        db_dir.mkdir()
        storage_dir.mkdir()

        db_file = db_dir / "db_backup_20260101.sql"
        storage_file = storage_dir / "storage_backup_20260101.zip"
        db_file.write_text("dummy")
        storage_file.write_bytes(b"dummy")

        manifest = {
            "timestamp": "20260101_000000Z",
            "db_backup_file": "db_backup_20260101.sql",
            "storage_backup_file": "storage_backup_20260101.zip",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
            "api_key": "sk-1234567890abcdef1234567890",
        }
        manifest_path = Path(tmpdir) / "backup_manifest_20260101.json"
        manifest_path.write_text(json.dumps(manifest))

        result = validate_manifest(str(manifest_path))
        assert result["ok"] is False
        assert any("secret" in e.lower() for e in result["errors"])


def test_manifest_bom_readable():
    from scripts.validate_backup_manifest import validate_manifest

    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "db"
        storage_dir = Path(tmpdir) / "storage"
        db_dir.mkdir()
        storage_dir.mkdir()

        db_file = db_dir / "db_backup_20260101.sql"
        storage_file = storage_dir / "storage_backup_20260101.zip"
        db_file.write_text("dummy")
        storage_file.write_bytes(b"dummy")

        manifest = {
            "timestamp": "20260101_000000Z",
            "db_backup_file": "db_backup_20260101.sql",
            "storage_backup_file": "storage_backup_20260101.zip",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = Path(tmpdir) / "backup_manifest_20260101.json"
        raw = json.dumps(manifest).encode("utf-8")
        bom_raw = b"\xef\xbb\xbf" + raw
        manifest_path.write_bytes(bom_raw)

        result = validate_manifest(str(manifest_path))
        assert result["ok"] is True


def test_manifest_not_found():
    from scripts.validate_backup_manifest import validate_manifest

    result = validate_manifest("/nonexistent/path/manifest.json")
    assert result["ok"] is False
    assert any("not found" in e for e in result["errors"])
    for e in result["errors"]:
        assert "/nonexistent" not in e
        assert "C:" not in e


def test_restore_dry_run_no_destructive_ops():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "db"
        storage_dir = Path(tmpdir) / "storage"
        db_dir.mkdir()
        storage_dir.mkdir()

        db_file = db_dir / "db_backup_20260101.sql"
        storage_file = storage_dir / "storage_backup_20260101.zip"
        db_file.write_text("dummy db")
        storage_file.write_bytes(b"dummy storage")

        manifest = {
            "timestamp": "20260101_000000Z",
            "db_backup_file": "db_backup_20260101.sql",
            "storage_backup_file": "storage_backup_20260101.zip",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = Path(tmpdir) / "backup_manifest_20260101.json"
        manifest_path.write_text(json.dumps(manifest))

        from scripts.validate_backup_manifest import validate_manifest
        result = validate_manifest(str(manifest_path))
        assert result["ok"] is True

        assert db_file.read_text() == "dummy db"
        assert storage_file.read_bytes() == b"dummy storage"


def test_restore_dry_run_missing_manifest_fails():
    from scripts.validate_backup_manifest import validate_manifest

    result = validate_manifest("/nonexistent/manifest.json")
    assert result["ok"] is False


def test_production_check_validate_manifest_script():
    from scripts.production_check import _check_validate_manifest_script
    result = _check_validate_manifest_script()
    assert result.status == "PASS"
    assert "present" in result.message


def test_production_check_maintenance_scripts_includes_validate():
    from scripts.production_check import _check_maintenance_scripts
    result = _check_maintenance_scripts()
    assert result.status == "PASS"
    assert "all present" in result.message


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell dry-run test requires Windows")
def test_powershell_dry_run_success():
    project_root = _get_project_root()
    script_path = project_root / "scripts" / "restore_all.ps1"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "db"
        storage_dir = Path(tmpdir) / "storage"
        db_dir.mkdir()
        storage_dir.mkdir()

        db_file = db_dir / "db_backup_test.sql"
        storage_file = storage_dir / "storage_backup_test.zip"
        db_file.write_text("dummy db content")
        storage_file.write_bytes(b"dummy storage content")

        manifest = {
            "timestamp": "20260101_000000Z",
            "db_backup_file": "db_backup_test.sql",
            "storage_backup_file": "storage_backup_test.zip",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = Path(tmpdir) / "backup_manifest_test.json"
        manifest_path.write_text(json.dumps(manifest))

        result = subprocess.run(
            [
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-ExecutionPolicy", "Bypass",
                "-File", str(script_path),
                "-ManifestPath", str(manifest_path),
                "-DryRun",
            ],
            capture_output=True, text=True, timeout=60,
            cwd=str(project_root),
        )

        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

        stdout = result.stdout
        assert "restore_postgres.ps1" not in stdout
        assert "restore_storage.ps1" not in stdout

        assert str(project_root) not in stdout
        assert tmpdir not in stdout

        assert db_file.read_text() == "dummy db content"
        assert storage_file.read_bytes() == b"dummy storage content"

        drill_files = sorted(
            (project_root / "artifacts" / "backups").glob("restore_drill_*.json"),
            key=lambda f: f.stat().st_mtime,
        )
        assert len(drill_files) >= 1
        latest_drill = drill_files[-1]
        drill_data = json.loads(latest_drill.read_text())
        assert drill_data["ok"] is True
        assert drill_data["dry_run"] is True
        assert drill_data["db_backup_present"] is True
        assert drill_data["storage_backup_present"] is True
        assert str(project_root) not in json.dumps(drill_data)
        assert tmpdir not in json.dumps(drill_data)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell dry-run test requires Windows")
def test_powershell_dry_run_missing_storage_fails():
    project_root = _get_project_root()
    script_path = project_root / "scripts" / "restore_all.ps1"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "db"
        storage_dir = Path(tmpdir) / "storage"
        db_dir.mkdir()
        storage_dir.mkdir()

        db_file = db_dir / "db_backup_test.sql"
        db_file.write_text("dummy db content")

        manifest = {
            "timestamp": "20260101_000000Z",
            "db_backup_file": "db_backup_test.sql",
            "storage_backup_file": "nonexistent_storage.zip",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = Path(tmpdir) / "backup_manifest_test.json"
        manifest_path.write_text(json.dumps(manifest))

        result = subprocess.run(
            [
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-ExecutionPolicy", "Bypass",
                "-File", str(script_path),
                "-ManifestPath", str(manifest_path),
                "-DryRun",
            ],
            capture_output=True, text=True, timeout=60,
            cwd=str(project_root),
        )

        assert result.returncode != 0

        stdout = result.stdout
        assert "restore_postgres.ps1" not in stdout
        assert "restore_storage.ps1" not in stdout

        assert db_file.read_text() == "dummy db content"

        drill_files = sorted(
            (project_root / "artifacts" / "backups").glob("restore_drill_*.json"),
            key=lambda f: f.stat().st_mtime,
        )
        assert len(drill_files) >= 1
        latest_drill = drill_files[-1]
        drill_data = json.loads(latest_drill.read_text())
        assert drill_data["ok"] is False
        assert drill_data["dry_run"] is True
        assert drill_data["storage_backup_present"] is False


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_gate_script_exists():
    project_root = _get_project_root()
    if not (project_root / "scripts").exists():
        pytest.skip("project root not accessible in container")
    rc_gate = project_root / "scripts" / "rc_gate.ps1"
    assert rc_gate.exists()


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_gate_no_confirm_restore():
    project_root = _get_project_root()
    if not (project_root / "scripts").exists():
        pytest.skip("project root not accessible in container")
    rc_gate = project_root / "scripts" / "rc_gate.ps1"
    content = rc_gate.read_text()
    assert "-ConfirmRestore" not in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_candidate_checklist_contains_validate_and_dryrun():
    project_root = _get_project_root()
    if not (project_root / "docs").exists():
        pytest.skip("project root not accessible in container")
    checklist = project_root / "docs" / "RELEASE_CANDIDATE_CHECKLIST.md"
    content = checklist.read_text()
    assert "validate_backup_manifest" in content
    assert "DryRun" in content or "-DryRun" in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_operations_runbook_no_secrets():
    project_root = _get_project_root()
    if not (project_root / "docs").exists():
        pytest.skip("project root not accessible in container")
    runbook = project_root / "docs" / "OPERATIONS_RUNBOOK.md"
    content = runbook.read_text()
    for pattern in ["sk-", "tp-", "API_KEY=", "Authorization:", "DATABASE_URL="]:
        assert pattern not in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_drill_file_selection_sorted():
    project_root = _get_project_root()
    if not (project_root / "apps").exists():
        pytest.skip("project root not accessible in container")
    test_file = project_root / "apps" / "api" / "tests" / "test_backup_lifecycle.py"
    content = test_file.read_text()
    assert "sorted(" in content
    assert "st_mtime" in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_gate_no_fail_warn_downgrade():
    project_root = _get_project_root()
    if not (project_root / "scripts").exists():
        pytest.skip("project root not accessible in container")
    rc_gate = project_root / "scripts" / "rc_gate.ps1"
    content = rc_gate.read_text()
    assert "RESULT: FAIL" not in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_gate_prod_check_throws_on_nonzero():
    project_root = _get_project_root()
    if not (project_root / "scripts").exists():
        pytest.skip("project root not accessible in container")
    rc_gate = project_root / "scripts" / "rc_gate.ps1"
    content = rc_gate.read_text()
    prod_check_block_start = content.find('"Production check"')
    assert prod_check_block_start > 0
    prod_check_block = content[prod_check_block_start:prod_check_block_start + 300]
    assert "LASTEXITCODE -ne 0" in prod_check_block
    assert "throw" in prod_check_block


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_checklist_manifest_path_project_relative():
    project_root = _get_project_root()
    if not (project_root / "docs").exists():
        pytest.skip("project root not accessible in container")
    checklist = project_root / "docs" / "RELEASE_CANDIDATE_CHECKLIST.md"
    content = checklist.read_text()
    assert "project-relative" in content or "project relative" in content.lower() or "相对路径" in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_gate_rejects_absolute_manifest_path():
    project_root = _get_project_root()
    if not (project_root / "scripts").exists():
        pytest.skip("project root not accessible in container")
    rc_gate = project_root / "scripts" / "rc_gate.ps1"
    content = rc_gate.read_text()
    assert "IsPathRooted" in content
    assert "ManifestPath must be project-relative" in content


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell test requires Windows")
def test_rc_gate_absolute_manifest_path_fails():
    project_root = _get_project_root()
    if not (project_root / "scripts").exists():
        pytest.skip("project root not accessible in container")
    rc_gate = project_root / "scripts" / "rc_gate.ps1"
    abs_path = "C:\\absolute\\path\\manifest.json"
    ps_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    if not Path(ps_exe).exists():
        pytest.skip("PowerShell not found at default path")
    env = os.environ.copy()
    env["Path"] = (
        os.environ.get("Path", "")
        + ";" + str(project_root / "apps" / "api" / ".venv" / "Scripts")
        + r";C:\Program Files\Docker\Docker\resources\bin"
    )
    result = subprocess.run(
        [
            ps_exe, "-ExecutionPolicy", "Bypass",
            "-File", str(rc_gate),
            "-ManifestPath", abs_path,
            "-SkipBackendTests", "-SkipFrontendBuild", "-SkipE2E", "-SkipProductionCheck",
        ],
        capture_output=True, text=True, timeout=60,
        cwd=str(project_root),
        env=env,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "ManifestPath must be project-relative" in combined
    assert abs_path not in combined


_REQUIRED_ENV_EXAMPLE_KEYS = [
    "CORS_ALLOWED_ORIGINS",
    "AUTH_ENABLED",
    "ALLOW_DEV_USER_HEADER",
    "SESSION_COOKIE_SECURE",
]


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_env_example_contains_production_config_keys():
    project_root = _get_project_root()
    env_example = project_root / ".env.example"
    if not env_example.exists():
        pytest.skip(".env.example not found")
    content = env_example.read_text()
    missing = [k for k in _REQUIRED_ENV_EXAMPLE_KEYS if f"{k}=" not in content]
    assert not missing, f".env.example missing production config keys: {missing}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_env_example_no_real_keys():
    project_root = _get_project_root()
    env_example = project_root / ".env.example"
    if not env_example.exists():
        pytest.skip(".env.example not found")
    content = env_example.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        value = stripped.split("=", 1)[1].strip()
        assert not value.startswith("sk-"), f".env.example contains sk- key in: {stripped}"
        assert not value.startswith("tp-"), f".env.example contains tp- key in: {stripped}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_gitignore_contains_env():
    project_root = _get_project_root()
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        pytest.skip(".gitignore not found")
    content = gitignore.read_text()
    lines = [l.strip() for l in content.splitlines()]
    assert ".env" in lines, ".gitignore does not contain .env entry"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_checklist_contains_rc_tag_security_checks():
    project_root = _get_project_root()
    if not (project_root / "docs").exists():
        pytest.skip("project root not accessible in container")
    checklist = project_root / "docs" / "RELEASE_CANDIDATE_CHECKLIST.md"
    content = checklist.read_text()
    assert "git ls-files .env" in content
    assert "SESSION_COOKIE_SECURE" in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_quick_gate_script_exists():
    project_root = _get_project_root()
    quick_gate = project_root / "scripts" / "quick_gate.ps1"
    assert quick_gate.exists(), "scripts/quick_gate.ps1 not found"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_quick_gate_no_full_pytest():
    project_root = _get_project_root()
    quick_gate = project_root / "scripts" / "quick_gate.ps1"
    if not quick_gate.exists():
        pytest.skip("quick_gate.ps1 not found")
    content = quick_gate.read_text()
    assert "pytest tests/" not in content
    assert "pytest tests/ -q" not in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_quick_gate_no_playwright():
    project_root = _get_project_root()
    quick_gate = project_root / "scripts" / "quick_gate.ps1"
    if not quick_gate.exists():
        pytest.skip("quick_gate.ps1 not found")
    content = quick_gate.read_text()
    assert "playwright test" not in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_quick_gate_no_restore():
    project_root = _get_project_root()
    quick_gate = project_root / "scripts" / "quick_gate.ps1"
    if not quick_gate.exists():
        pytest.skip("quick_gate.ps1 not found")
    content = quick_gate.read_text()
    assert "restore_all.ps1" not in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_checklist_contains_level_tiers():
    project_root = _get_project_root()
    if not (project_root / "docs").exists():
        pytest.skip("project root not accessible in container")
    checklist = project_root / "docs" / "RELEASE_CANDIDATE_CHECKLIST.md"
    content = checklist.read_text()
    assert "Level 1" in content
    assert "Level 2" in content
    assert "Level 3" in content
    assert "Level 4" in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_operations_runbook_contains_pytest_hang_recovery():
    project_root = _get_project_root()
    if not (project_root / "docs").exists():
        pytest.skip("project root not accessible in container")
    runbook = project_root / "docs" / "OPERATIONS_RUNBOOK.md"
    content = runbook.read_text()
    assert "TRUNCATE" in content
    assert "pg_terminate_backend" in content
    assert "pytest" in content.lower() and "hang" in content.lower()


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_notes_exists():
    project_root = _get_project_root()
    rn = project_root / "docs" / "RELEASE_NOTES_v1.0.0-rc.1.md"
    assert rn.exists(), "docs/RELEASE_NOTES_v1.0.0-rc.1.md not found"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_notes_no_secrets():
    project_root = _get_project_root()
    rn = project_root / "docs" / "RELEASE_NOTES_v1.0.0-rc.1.md"
    if not rn.exists():
        pytest.skip("RELEASE_NOTES not found")
    content = rn.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("-") or stripped.startswith(">"):
            continue
        if "=" not in stripped:
            continue
        value = stripped.split("=", 1)[1].strip()
        assert not value.startswith("sk-"), f"Release Notes contains sk- key in: {stripped}"
        assert not value.startswith("tp-"), f"Release Notes contains tp- key in: {stripped}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_readme_links_release_notes():
    project_root = _get_project_root()
    readme = project_root / "README.md"
    content = readme.read_text()
    assert "RELEASE_NOTES_v1.0.0-rc.1" in content


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_notes_no_unverified_all_checks_passed():
    project_root = _get_project_root()
    rn = project_root / "docs" / "RELEASE_NOTES_v1.0.0-rc.1.md"
    if not rn.exists():
        pytest.skip("RELEASE_NOTES not found")
    content = rn.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if "ALL CHECKS PASSED" in stripped and "Phase" not in stripped:
            pytest.fail(f"Release Notes contains unverified 'ALL CHECKS PASSED' without phase attribution: {stripped}")


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_notes_no_fixed_narrow_test_count():
    project_root = _get_project_root()
    rn = project_root / "docs" / "RELEASE_NOTES_v1.0.0-rc.1.md"
    if not rn.exists():
        pytest.skip("RELEASE_NOTES not found")
    content = rn.read_text()
    import re
    fragile_patterns = [r"\d+ passed\s*\("]
    for pat in fragile_patterns:
        if re.search(pat, content):
            pytest.fail(f"Release Notes contains fragile fixed test count matching '{pat}'")


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_notes_no_future_tense_phase43():
    project_root = _get_project_root()
    rn = project_root / "docs" / "RELEASE_NOTES_v1.0.0-rc.1.md"
    if not rn.exists():
        pytest.skip("RELEASE_NOTES not found")
    content = rn.read_text()
    future_patterns = [
        "将在 Phase 43 执行",
        "将在 Phase 43",
        "Phase 43 将",
    ]
    for pat in future_patterns:
        assert pat not in content, f"RELEASE_NOTES still contains future-tense phrase: {pat}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_evidence_exists():
    project_root = _get_project_root()
    evidence = project_root / "docs" / "RC_EVIDENCE_v1.0.0-rc.1.md"
    assert evidence.exists(), "docs/RC_EVIDENCE_v1.0.0-rc.1.md not found"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_evidence_no_secrets():
    project_root = _get_project_root()
    evidence = project_root / "docs" / "RC_EVIDENCE_v1.0.0-rc.1.md"
    if not evidence.exists():
        pytest.skip("RC_EVIDENCE not found")
    content = evidence.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("-") or stripped.startswith(">"):
            continue
        if "=" not in stripped:
            continue
        value = stripped.split("=", 1)[1].strip()
        assert not value.startswith("sk-"), f"RC_EVIDENCE contains sk- key in: {stripped}"
        assert not value.startswith("tp-"), f"RC_EVIDENCE contains tp- key in: {stripped}"
    for forbidden in ["DATABASE_URL=postgres", "API_KEY=sk-"]:
        assert forbidden not in content, f"RC_EVIDENCE contains forbidden pattern: {forbidden}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_evidence_contains_artifact_filenames():
    project_root = _get_project_root()
    evidence = project_root / "docs" / "RC_EVIDENCE_v1.0.0-rc.1.md"
    if not evidence.exists():
        pytest.skip("RC_EVIDENCE not found")
    content = evidence.read_text()
    assert "backup_manifest_" in content, "RC_EVIDENCE missing backup_manifest_ filename"
    assert "restore_drill_" in content, "RC_EVIDENCE missing restore_drill_ filename"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_release_notes_no_complete_gate_with_playwright_missing():
    project_root = _get_project_root()
    rn = project_root / "docs" / "RELEASE_NOTES_v1.0.0-rc.1.md"
    if not rn.exists():
        pytest.skip("RELEASE_NOTES not found")
    content = rn.read_text()
    has_complete_gate = "完整 RC gate" in content or "完整RC gate" in content
    has_playwright_not_run = "Playwright" in content and ("未执行" in content or "未在" in content)
    assert not (has_complete_gate and has_playwright_not_run), (
        "RELEASE_NOTES claims '完整 RC gate' while also stating Playwright was not executed — contradiction"
    )


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_evidence_e2e_status_documented():
    project_root = _get_project_root()
    evidence = project_root / "docs" / "RC_EVIDENCE_v1.0.0-rc.1.md"
    if not evidence.exists():
        pytest.skip("RC_EVIDENCE not found")
    content = evidence.read_text()
    has_e2e_resolved = (
        "E2E Exception Resolved" in content
        or "E2E 例外已消除" in content
        or "E2E 例外" in content
    )
    has_playwright_passed = "103 passed" in content or "Playwright" in content
    assert has_e2e_resolved or has_playwright_passed, (
        "RC_EVIDENCE must document E2E status (exception resolved or Playwright passed)"
    )


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_rc_evidence_production_check_count_consistent():
    project_root = _get_project_root()
    evidence = project_root / "docs" / "RC_EVIDENCE_v1.0.0-rc.1.md"
    if not evidence.exists():
        pytest.skip("RC_EVIDENCE not found")
    content = evidence.read_text()
    import re
    count_patterns = re.findall(r'(\d+)/\d+\s+ALL CHECKS PASSED', content)
    if len(count_patterns) >= 2:
        unique_counts = set(count_patterns)
        assert len(unique_counts) == 1, (
            f"RC_EVIDENCE contains conflicting production_check counts: {count_patterns}. "
            "Must explain the difference or use consistent numbers."
        )


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_deployment_runbook_exists():
    project_root = _get_project_root()
    runbook = project_root / "docs" / "DEPLOYMENT_RUNBOOK_v1.0.0.md"
    assert runbook.exists(), "docs/DEPLOYMENT_RUNBOOK_v1.0.0.md must exist"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_deployment_evidence_exists():
    project_root = _get_project_root()
    evidence = project_root / "docs" / "DEPLOYMENT_EVIDENCE_v1.0.0.md"
    assert evidence.exists(), "docs/DEPLOYMENT_EVIDENCE_v1.0.0.md must exist"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_deployment_docs_no_secrets():
    project_root = _get_project_root()
    secret_patterns = [
        re.compile(r'sk-[a-zA-Z0-9]{20,}'),
        re.compile(r'tp-[a-zA-Z0-9]{20,}'),
        re.compile(r'DATABASE_URL\s*=\s*postgresql://[^\s<]{10,}(?<!localhost/research)(?<!localhost/research_db)'),
    ]
    for doc_name in ["DEPLOYMENT_RUNBOOK_v1.0.0.md", "DEPLOYMENT_EVIDENCE_v1.0.0.md"]:
        doc = project_root / "docs" / doc_name
        if not doc.exists():
            continue
        content = doc.read_text()
        for pat in secret_patterns:
            match = pat.search(content)
            assert not match, f"{doc_name} contains secret-like value: {match.group()[:20]}..."


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_deployment_evidence_contains_artifact_filenames():
    project_root = _get_project_root()
    evidence = project_root / "docs" / "DEPLOYMENT_EVIDENCE_v1.0.0.md"
    if not evidence.exists():
        pytest.skip("DEPLOYMENT_EVIDENCE not found")
    content = evidence.read_text()
    assert "backup_manifest_" in content, "DEPLOYMENT_EVIDENCE must reference backup_manifest_ filename"
    assert "restore_drill_" in content, "DEPLOYMENT_EVIDENCE must reference restore_drill_ filename"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_deployment_runbook_contains_required_sections():
    project_root = _get_project_root()
    runbook = project_root / "docs" / "DEPLOYMENT_RUNBOOK_v1.0.0.md"
    if not runbook.exists():
        pytest.skip("DEPLOYMENT_RUNBOOK not found")
    content = runbook.read_text()
    required = [("rollback", "回滚"), ("restore dry-run", None), ("production_check", None)]
    missing = []
    for en, zh in required:
        if en.lower() not in content.lower() and (zh is None or zh not in content):
            missing.append(en)
    assert not missing, f"DEPLOYMENT_RUNBOOK missing required sections: {missing}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ci_workflow_exists():
    project_root = _get_project_root()
    ci_yml = project_root / ".github" / "workflows" / "ci.yml"
    assert ci_yml.exists(), ".github/workflows/ci.yml must exist"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ci_workflow_no_confirm_restore():
    project_root = _get_project_root()
    ci_yml = project_root / ".github" / "workflows" / "ci.yml"
    if not ci_yml.exists():
        pytest.skip("ci.yml not found")
    content = ci_yml.read_text()
    assert "ConfirmRestore" not in content, "ci.yml must not contain ConfirmRestore"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ci_workflow_no_env_reference():
    project_root = _get_project_root()
    ci_yml = project_root / ".github" / "workflows" / "ci.yml"
    if not ci_yml.exists():
        pytest.skip("ci.yml not found")
    content = ci_yml.read_text()
    assert ".env" not in content, "ci.yml must not reference .env"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ci_workflow_contains_secret_scan():
    project_root = _get_project_root()
    ci_yml = project_root / ".github" / "workflows" / "ci.yml"
    if not ci_yml.exists():
        pytest.skip("ci.yml not found")
    content = ci_yml.read_text()
    assert "check_docs_secrets.py" in content, "ci.yml must include check_docs_secrets.py"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ci_workflow_contains_mojibake_scan():
    project_root = _get_project_root()
    ci_yml = project_root / ".github" / "workflows" / "ci.yml"
    if not ci_yml.exists():
        pytest.skip("ci.yml not found")
    content = ci_yml.read_text()
    assert "check_frontend_mojibake.py" in content, "ci.yml must include check_frontend_mojibake.py"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ci_workflow_contains_npm_build():
    project_root = _get_project_root()
    ci_yml = project_root / ".github" / "workflows" / "ci.yml"
    if not ci_yml.exists():
        pytest.skip("ci.yml not found")
    content = ci_yml.read_text()
    assert "npm run build" in content, "ci.yml must include npm run build"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ci_docs_exist_and_no_secrets():
    project_root = _get_project_root()
    ci_runbook = project_root / "docs" / "CI_CD_RUNBOOK.md"
    ops_backlog = project_root / "docs" / "OPERATIONS_BACKLOG.md"
    found = False
    for doc in [ci_runbook, ops_backlog]:
        if doc.exists():
            found = True
            content = doc.read_text()
            for pat in [re.compile(r'sk-[a-zA-Z0-9]{20,}'), re.compile(r'tp-[a-zA-Z0-9]{20,}')]:
                match = pat.search(content)
                assert not match, f"{doc.name} contains secret-like value: {match.group()[:20]}..."
    assert found, "At least one of CI_CD_RUNBOOK.md or OPERATIONS_BACKLOG.md must exist"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_backup_freshness_no_manifest():
    project_root = _get_project_root()
    script = project_root / "scripts" / "check_backup_freshness.py"
    if not script.exists():
        pytest.skip("check_backup_freshness.py not found")
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_dir = Path(tmpdir) / "backups"
        empty_dir.mkdir()
        result = subprocess.run(
            [sys.executable, str(script), "--backups-dir", str(empty_dir)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["latest_manifest"] is None
        assert len(data["warnings"]) > 0


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_backup_freshness_recent_manifest_ok():
    project_root = _get_project_root()
    script = project_root / "scripts" / "check_backup_freshness.py"
    if not script.exists():
        pytest.skip("check_backup_freshness.py not found")
    with tempfile.TemporaryDirectory() as tmpdir:
        backups_dir = Path(tmpdir) / "backups"
        backups_dir.mkdir()
        now_iso = datetime.now(timezone.utc).isoformat()
        manifest = {"timestamp": now_iso, "app_version": "1.0.0"}
        manifest_path = backups_dir / "backup_manifest_20260527.json"
        manifest_path.write_text(json.dumps(manifest))
        result = subprocess.run(
            [sys.executable, str(script), "--backups-dir", str(backups_dir), "--max-age-hours", "24"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["latest_manifest"] == "backup_manifest_20260527.json"
        assert data["age_hours"] <= 24


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_backup_freshness_old_manifest_warns_or_fails():
    project_root = _get_project_root()
    script = project_root / "scripts" / "check_backup_freshness.py"
    if not script.exists():
        pytest.skip("check_backup_freshness.py not found")
    with tempfile.TemporaryDirectory() as tmpdir:
        backups_dir = Path(tmpdir) / "backups"
        backups_dir.mkdir()
        old_ts = (datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=48)).isoformat()
        manifest = {"timestamp": old_ts, "app_version": "1.0.0"}
        manifest_path = backups_dir / "backup_manifest_old.json"
        manifest_path.write_text(json.dumps(manifest))
        result = subprocess.run(
            [sys.executable, str(script), "--backups-dir", str(backups_dir), "--max-age-hours", "24"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["age_hours"] > 24
        assert len(data["warnings"]) > 0


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_backup_freshness_outputs_filename_only():
    project_root = _get_project_root()
    script = project_root / "scripts" / "check_backup_freshness.py"
    if not script.exists():
        pytest.skip("check_backup_freshness.py not found")
    with tempfile.TemporaryDirectory() as tmpdir:
        backups_dir = Path(tmpdir) / "backups"
        backups_dir.mkdir()
        now_iso = datetime.now(timezone.utc).isoformat()
        manifest = {"timestamp": now_iso, "app_version": "1.0.0"}
        manifest_path = backups_dir / "backup_manifest_test.json"
        manifest_path.write_text(json.dumps(manifest))
        result = subprocess.run(
            [sys.executable, str(script), "--backups-dir", str(backups_dir)],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        output_text = result.stdout
        assert str(backups_dir) not in output_text
        assert str(tmpdir) not in output_text
        if data["latest_manifest"]:
            assert "/" not in data["latest_manifest"]
            assert "\\" not in data["latest_manifest"]


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ops_check_script_exists():
    project_root = _get_project_root()
    ops_check = project_root / "scripts" / "ops_check.ps1"
    assert ops_check.exists(), "scripts/ops_check.ps1 must exist"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ops_check_no_confirm_restore():
    project_root = _get_project_root()
    ops_check = project_root / "scripts" / "ops_check.ps1"
    if not ops_check.exists():
        pytest.skip("ops_check.ps1 not found")
    content = ops_check.read_text()
    assert "ConfirmRestore" not in content, "ops_check.ps1 must not contain ConfirmRestore"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ops_check_no_backup_or_restore():
    project_root = _get_project_root()
    ops_check = project_root / "scripts" / "ops_check.ps1"
    if not ops_check.exists():
        pytest.skip("ops_check.ps1 not found")
    content = ops_check.read_text()
    forbidden = ["backup_all", "restore_all", "restore_postgres", "restore_storage"]
    for word in forbidden:
        assert word not in content, f"ops_check.ps1 must not execute {word}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_operations_monitoring_doc_exists():
    project_root = _get_project_root()
    doc = project_root / "docs" / "OPERATIONS_MONITORING.md"
    assert doc.exists(), "docs/OPERATIONS_MONITORING.md must exist"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_operations_monitoring_doc_no_secrets():
    project_root = _get_project_root()
    doc = project_root / "docs" / "OPERATIONS_MONITORING.md"
    if not doc.exists():
        pytest.skip("OPERATIONS_MONITORING.md not found")
    content = doc.read_text()
    for pat in [re.compile(r'sk-[a-zA-Z0-9]{20,}'), re.compile(r'tp-[a-zA-Z0-9]{20,}')]:
        match = pat.search(content)
        assert not match, f"OPERATIONS_MONITORING.md contains secret-like value: {match.group()[:20]}..."
    for forbidden in ["DATABASE_URL=postgres", "API_KEY=sk-"]:
        assert forbidden not in content, f"OPERATIONS_MONITORING.md contains forbidden pattern: {forbidden}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ops_check_no_auth_register_or_login():
    project_root = _get_project_root()
    ops_check = project_root / "scripts" / "ops_check.ps1"
    if not ops_check.exists():
        pytest.skip("ops_check.ps1 not found")
    content = ops_check.read_text()
    assert "auth/register" not in content, "ops_check.ps1 must not call /auth/register"
    assert "auth/login" not in content, "ops_check.ps1 must not call /auth/login"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ops_check_no_post_methods():
    project_root = _get_project_root()
    ops_check = project_root / "scripts" / "ops_check.ps1"
    if not ops_check.exists():
        pytest.skip("ops_check.ps1 not found")
    content = ops_check.read_text()
    assert "-Method POST" not in content, "ops_check.ps1 must not use -Method POST"
    assert "Invoke-RestMethod -Method POST" not in content, "ops_check.ps1 must not use Invoke-RestMethod -Method POST"
    assert "Invoke-WebRequest -Method POST" not in content, "ops_check.ps1 must not use Invoke-WebRequest -Method POST"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_ops_check_no_state_writes():
    project_root = _get_project_root()
    ops_check = project_root / "scripts" / "ops_check.ps1"
    if not ops_check.exists():
        pytest.skip("ops_check.ps1 not found")
    content = ops_check.read_text()
    forbidden_writes = [
        "ConvertTo-Json",
        "SessionVariable",
        "WebSession",
        "X-User-Id",
    ]
    for word in forbidden_writes:
        assert word not in content, f"ops_check.ps1 must not contain state-writing pattern: {word}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_v1_0_1_backlog_exists():
    project_root = _get_project_root()
    backlog = project_root / "docs" / "V1_0_1_BACKLOG.md"
    assert backlog.exists(), "docs/V1_0_1_BACKLOG.md must exist"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_v1_0_1_backlog_no_secrets():
    project_root = _get_project_root()
    backlog = project_root / "docs" / "V1_0_1_BACKLOG.md"
    if not backlog.exists():
        pytest.skip("V1_0_1_BACKLOG.md not found")
    content = backlog.read_text()
    for pat in [re.compile(r'sk-[a-zA-Z0-9]{20,}'), re.compile(r'tp-[a-zA-Z0-9]{20,}')]:
        match = pat.search(content)
        assert not match, f"V1_0_1_BACKLOG.md contains secret-like value: {match.group()[:20]}..."
    for forbidden in ["DATABASE_URL=postgres", "API_KEY=sk-"]:
        assert forbidden not in content, f"V1_0_1_BACKLOG.md contains forbidden pattern: {forbidden}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_v1_0_1_backlog_contains_priority_levels():
    project_root = _get_project_root()
    backlog = project_root / "docs" / "V1_0_1_BACKLOG.md"
    if not backlog.exists():
        pytest.skip("V1_0_1_BACKLOG.md not found")
    content = backlog.read_text()
    for level in ["P0", "P1", "P2", "P3"]:
        assert level in content, f"V1_0_1_BACKLOG.md must contain {level} section"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_v1_0_1_backlog_contains_required_items():
    project_root = _get_project_root()
    backlog = project_root / "docs" / "V1_0_1_BACKLOG.md"
    if not backlog.exists():
        pytest.skip("V1_0_1_BACKLOG.md not found")
    content = backlog.read_text().lower()
    required_items = [
        "playwright",
        "backup freshness",
        "restore dry-run",
        "storage orphan",
        "ops token",
    ]
    missing = [item for item in required_items if item not in content]
    assert not missing, f"V1_0_1_BACKLOG.md missing required items: {missing}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_post_release_issue_template_exists():
    project_root = _get_project_root()
    template = project_root / "docs" / "POST_RELEASE_ISSUE_TEMPLATE.md"
    assert template.exists(), "docs/POST_RELEASE_ISSUE_TEMPLATE.md must exist"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_post_release_issue_template_no_secrets():
    project_root = _get_project_root()
    template = project_root / "docs" / "POST_RELEASE_ISSUE_TEMPLATE.md"
    if not template.exists():
        pytest.skip("POST_RELEASE_ISSUE_TEMPLATE.md not found")
    content = template.read_text()
    for pat in [re.compile(r'sk-[a-zA-Z0-9]{20,}'), re.compile(r'tp-[a-zA-Z0-9]{20,}')]:
        match = pat.search(content)
        assert not match, f"POST_RELEASE_ISSUE_TEMPLATE.md contains secret-like value: {match.group()[:20]}..."
    for forbidden in ["DATABASE_URL=postgres", "API_KEY=sk-"]:
        assert forbidden not in content, f"POST_RELEASE_ISSUE_TEMPLATE.md contains forbidden pattern: {forbidden}"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_readme_links_v1_0_1_backlog():
    project_root = _get_project_root()
    readme = project_root / "README.md"
    content = readme.read_text()
    assert "V1_0_1_BACKLOG" in content, "README.md must link to V1_0_1_BACKLOG.md"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_env_example_documents_production_https_cookie():
    project_root = _get_project_root()
    env_example = project_root / ".env.example"
    if not env_example.exists():
        pytest.skip(".env.example not found")
    content = env_example.read_text()
    assert "SESSION_COOKIE_SECURE" in content, ".env.example must document SESSION_COOKIE_SECURE"
    assert "ENV=" in content or "ENV=" in content, ".env.example must document ENV variable"
    has_https_hint = "HTTPS" in content or "https" in content
    assert has_https_hint, ".env.example must mention HTTPS for production cookie"


@pytest.mark.skipif(not Path("/.dockerenv").exists() and sys.platform != "win32", reason="RC gate/docs tests require project root access")
def test_v1_0_1_backlog_marks_cors_cookie_item():
    project_root = _get_project_root()
    backlog = project_root / "docs" / "V1_0_1_BACKLOG.md"
    if not backlog.exists():
        pytest.skip("V1_0_1_BACKLOG.md not found")
    content = backlog.read_text()
    assert "Phase 50" in content, "V1_0_1_BACKLOG.md must mark CORS/cookie item with Phase 50"
