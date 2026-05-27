from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
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
def test_rc_evidence_contains_e2e_exception():
    project_root = _get_project_root()
    evidence = project_root / "docs" / "RC_EVIDENCE_v1.0.0-rc.1.md"
    if not evidence.exists():
        pytest.skip("RC_EVIDENCE not found")
    content = evidence.read_text()
    has_e2e_exception = (
        "E2E exception" in content
        or "E2E 例外" in content
        or "E2E 未执行" in content
        or "Playwright E2E" in content and "未执行" in content
    )
    assert has_e2e_exception, "RC_EVIDENCE must contain E2E exception / E2E 未执行 explanation"


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
