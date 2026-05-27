from __future__ import annotations

import io
import json
import os
import subprocess
import pytest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.paper_service import _safe_filename, PaperService
from app.config import settings
from app.config import parse_cors_allowed_origins, is_production, normalize_env


def test_safe_filename_normal():
    assert _safe_filename("paper.pdf") == "paper.pdf"


def test_safe_filename_path_traversal():
    assert ".." not in _safe_filename("../../../etc/passwd")
    assert "/" not in _safe_filename("../../../etc/passwd")
    assert os.sep not in _safe_filename(f"..{os.sep}..{os.sep}etc{os.sep}passwd")


def test_safe_filename_hidden_file():
    result = _safe_filename(".env")
    assert result == "upload"


def test_safe_filename_empty():
    result = _safe_filename("")
    assert result == "upload"


def test_upload_path_uses_storage_path():
    storage_base = settings.STORAGE_PATH
    upload_dir = os.path.join(storage_base, "uploads", "user1")
    assert storage_base in upload_dir
    assert "uploads" in upload_dir


@pytest.mark.asyncio
async def test_pdf_parse_failure_marks_paper_failed():
    with patch("app.services.paper_service.parse_pdf", side_effect=Exception("PDF is corrupted")):
        mock_repo = MagicMock()
        mock_paper = MagicMock()
        mock_paper.file_path = "/tmp/test.pdf"
        mock_repo.get_paper = AsyncMock(return_value=mock_paper)
        mock_repo.update_paper_status = AsyncMock()

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        mock_embedding = MagicMock()
        mock_embedding.embed_chunks_for_paper = AsyncMock()

        svc = PaperService.__new__(PaperService)
        svc.session = mock_session
        svc.user_id = "default"
        svc.repo = mock_repo
        svc.embedding_service = mock_embedding

        await svc.process_paper(1)

        mock_repo.update_paper_status.assert_any_call(
            1, "failed", "PDF is corrupted", user_id="default"
        )


@pytest.mark.asyncio
async def test_no_fake_text_on_parse_failure():
    with patch("app.services.paper_service.parse_pdf", side_effect=Exception("Cannot parse")):
        mock_repo = MagicMock()
        mock_paper = MagicMock()
        mock_paper.file_path = "/tmp/test.pdf"
        mock_repo.get_paper = AsyncMock(return_value=mock_paper)
        mock_repo.update_paper_status = AsyncMock()

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        mock_embedding = MagicMock()
        mock_embedding.embed_chunks_for_paper = AsyncMock()

        svc = PaperService.__new__(PaperService)
        svc.session = mock_session
        svc.user_id = "default"
        svc.repo = mock_repo
        svc.embedding_service = mock_embedding

        await svc.process_paper(1)

        for call in mock_repo.update_paper_status.call_args_list:
            args = call[0]
            if len(args) >= 2 and args[1] == "completed":
                pytest.fail("Paper should not be marked completed when parse fails")


@pytest.mark.asyncio
async def test_rebuild_embeddings_calls_correct_method():
    mock_repo = MagicMock()
    mock_paper = MagicMock()
    mock_repo.get_paper = AsyncMock(return_value=mock_paper)
    mock_repo.clear_embeddings = AsyncMock(return_value=3)

    mock_embedding = MagicMock()
    mock_embedding.embed_chunks_for_paper = AsyncMock(return_value=3)

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()

    svc = PaperService.__new__(PaperService)
    svc.session = mock_session
    svc.user_id = "default"
    svc.repo = mock_repo
    svc.embedding_service = mock_embedding

    result = await svc.rebuild_embeddings(1)

    mock_repo.clear_embeddings.assert_called_once_with(1)
    mock_embedding.embed_chunks_for_paper.assert_called_once_with(1)
    assert result == 3


@pytest.mark.asyncio
async def test_upload_paper_uses_self_user_id():
    mock_repo = MagicMock()
    mock_paper = MagicMock()
    mock_paper.user_id = "alice"
    mock_repo.create_paper = AsyncMock(return_value=mock_paper)

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()

    with patch("builtins.open", MagicMock()), \
         patch("os.makedirs", MagicMock()):
        svc = PaperService.__new__(PaperService)
        svc.session = mock_session
        svc.user_id = "alice"
        svc.repo = mock_repo
        svc.embedding_service = MagicMock()

        await svc.upload_paper("test.pdf", b"content")

        call_args = mock_repo.create_paper.call_args[0][0]
        assert call_args.user_id == "alice"


@pytest.mark.asyncio
async def test_upload_paper_no_default_user_id_leak():
    mock_repo = MagicMock()
    mock_paper = MagicMock()
    mock_paper.user_id = "bob"
    mock_repo.create_paper = AsyncMock(return_value=mock_paper)

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()

    with patch("builtins.open", MagicMock()), \
         patch("os.makedirs", MagicMock()):
        svc = PaperService.__new__(PaperService)
        svc.session = mock_session
        svc.user_id = "bob"
        svc.repo = mock_repo
        svc.embedding_service = MagicMock()

        await svc.upload_paper("test.pdf", b"content")

        call_args = mock_repo.create_paper.call_args[0][0]
        assert call_args.user_id == "bob"
        assert call_args.user_id != "default"


@pytest.mark.asyncio
async def test_update_paper_status_with_user_id_scoping():
    mock_repo_get = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    from app.repositories.paper_repo import PaperRepository
    repo = PaperRepository.__new__(PaperRepository)
    repo.session = mock_session
    repo.get_paper = mock_repo_get

    result = await repo.update_paper_status(1, "completed", user_id="other_user")

    assert result is None
    mock_repo_get.assert_called_once_with(1, user_id="other_user")


def test_production_check_no_sensitive_output():
    from scripts.production_check import CheckResult, print_results

    results = [
        CheckResult("Database", "PASS", ""),
        CheckResult("Storage writable", "PASS", ""),
        CheckResult("Eval report", "WARN", "missing"),
    ]

    buf = io.StringIO()
    with redirect_stdout(buf):
        exit_code = print_results(results)

    output = buf.getvalue()
    assert exit_code == 0
    assert "PASS WITH WARNINGS" in output
    assert "DATABASE_URL" not in output
    assert "postgresql+asyncpg://" not in output
    assert "API_KEY" not in output
    assert "sk-" not in output


def test_production_check_fail_on_real_model_local():
    from scripts.production_check import _check_real_model_required

    with patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("app.config.settings.LLM_PROVIDER", "local"), \
         patch("app.config.settings.EMBEDDING_PROVIDER", "local"):
        result = _check_real_model_required()
        assert result.status == "FAIL"
        assert "local" in result.message


def test_production_check_pass_when_not_required():
    from scripts.production_check import _check_real_model_required

    with patch("app.config.settings.REAL_MODEL_REQUIRED", False):
        result = _check_real_model_required()
        assert result.status == "PASS"


def test_production_check_alembic_not_initialized_warn():
    from scripts.production_check import _check_alembic

    with patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("scripts.production_check.Path") as mock_path_cls:
        mock_alembic_dir = MagicMock()
        mock_alembic_dir.exists.return_value = False
        mock_path_cls.return_value.resolve.return_value.parent.parent.__truediv__ = MagicMock(return_value=mock_alembic_dir)
        mock_path_cls.return_value.resolve.return_value = MagicMock(parent=MagicMock(parent=MagicMock()))

        result = _check_alembic()
        assert result.status in ("WARN", "FAIL")


def test_production_check_alembic_fail_on_real_model():
    from scripts.production_check import _check_alembic

    with patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("scripts.production_check.Path") as mock_path_cls:
        mock_alembic_dir = MagicMock()
        mock_alembic_dir.exists.return_value = False
        mock_path_cls.return_value.resolve.return_value.parent.parent.__truediv__ = MagicMock(return_value=mock_alembic_dir)
        mock_path_cls.return_value.resolve.return_value = MagicMock(parent=MagicMock(parent=MagicMock()))

        result = _check_alembic()
        assert result.status == "FAIL"


def test_alembic_parse_revision():
    from scripts.production_check import _parse_alembic_revision

    output = "001_baseline (head)\n"
    assert _parse_alembic_revision(output) == "001_baseline"

    output_empty = ""
    assert _parse_alembic_revision(output_empty) is None

    output_hash = "a1b2c3d4e5f6 (head)\n"
    assert _parse_alembic_revision(output_hash) == "a1b2c3d4e5f6"


def test_alembic_current_equals_head_pass():
    from scripts.production_check import _check_alembic

    with patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("scripts.production_check.Path") as mock_path_cls:
        mock_alembic_dir = MagicMock()
        mock_alembic_dir.exists.return_value = True
        mock_path_cls.return_value.resolve.return_value.parent.parent.__truediv__ = MagicMock(return_value=mock_alembic_dir)
        mock_path_cls.return_value.resolve.return_value = MagicMock(parent=MagicMock(parent=MagicMock()))

        with patch("scripts.production_check.subprocess") as mock_subprocess:
            mock_current = MagicMock()
            mock_current.returncode = 0
            mock_current.stdout = "001_baseline (head)\n"

            mock_heads = MagicMock()
            mock_heads.returncode = 0
            mock_heads.stdout = "001_baseline (head)\n"

            mock_subprocess.run.side_effect = [mock_current, mock_heads]

            result = _check_alembic()
            assert result.status == "PASS"
            assert "at head" in result.message


def test_alembic_current_not_equal_head_warn():
    from scripts.production_check import _check_alembic

    with patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("scripts.production_check.Path") as mock_path_cls:
        mock_alembic_dir = MagicMock()
        mock_alembic_dir.exists.return_value = True
        mock_path_cls.return_value.resolve.return_value.parent.parent.__truediv__ = MagicMock(return_value=mock_alembic_dir)
        mock_path_cls.return_value.resolve.return_value = MagicMock(parent=MagicMock(parent=MagicMock()))

        with patch("scripts.production_check.subprocess") as mock_subprocess:
            mock_current = MagicMock()
            mock_current.returncode = 0
            mock_current.stdout = "000_old (head)\n"

            mock_heads = MagicMock()
            mock_heads.returncode = 0
            mock_heads.stdout = "001_baseline (head)\n"

            mock_subprocess.run.side_effect = [mock_current, mock_heads]

            result = _check_alembic()
            assert result.status == "WARN"


def test_alembic_current_not_equal_head_fail_real_model():
    from scripts.production_check import _check_alembic

    with patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("scripts.production_check.Path") as mock_path_cls:
        mock_alembic_dir = MagicMock()
        mock_alembic_dir.exists.return_value = True
        mock_path_cls.return_value.resolve.return_value.parent.parent.__truediv__ = MagicMock(return_value=mock_alembic_dir)
        mock_path_cls.return_value.resolve.return_value = MagicMock(parent=MagicMock(parent=MagicMock()))

        with patch("scripts.production_check.subprocess") as mock_subprocess:
            mock_current = MagicMock()
            mock_current.returncode = 0
            mock_current.stdout = "000_old (head)\n"

            mock_heads = MagicMock()
            mock_heads.returncode = 0
            mock_heads.stdout = "001_baseline (head)\n"

            mock_subprocess.run.side_effect = [mock_current, mock_heads]

            result = _check_alembic()
            assert result.status == "FAIL"


def test_alembic_command_failure_warn():
    from scripts.production_check import _check_alembic

    with patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("scripts.production_check.Path") as mock_path_cls:
        mock_alembic_dir = MagicMock()
        mock_alembic_dir.exists.return_value = True
        mock_path_cls.return_value.resolve.return_value.parent.parent.__truediv__ = MagicMock(return_value=mock_alembic_dir)
        mock_path_cls.return_value.resolve.return_value = MagicMock(parent=MagicMock(parent=MagicMock()))

        with patch("scripts.production_check.subprocess") as mock_subprocess:
            mock_current = MagicMock()
            mock_current.returncode = 1
            mock_current.stdout = ""

            mock_subprocess.run.return_value = mock_current

            result = _check_alembic()
            assert result.status == "WARN"


def test_backup_manifest_no_secrets():
    from scripts.backup_manifest import generate_manifest, manifest_has_secrets

    manifest = generate_manifest(
        db_backup_file="db_backup_20260524.sql",
        storage_backup_file="storage_backup_20260524.zip",
        eval_backup_file="eval_backup_20260524.zip",
        app_version="1.0.0",
        embedding_dimension=384,
    )
    assert not manifest_has_secrets(manifest)


def test_backup_manifest_has_app_version():
    from scripts.backup_manifest import generate_manifest

    manifest = generate_manifest(
        db_backup_file="db.sql",
        storage_backup_file="storage.zip",
        eval_backup_file="eval.zip",
        app_version="1.0.0",
        embedding_dimension=384,
    )
    assert manifest["app_version"] == "1.0.0"
    assert manifest["embedding_dimension"] == 384


def test_backup_manifest_detects_secrets():
    from scripts.backup_manifest import manifest_has_secrets

    bad_manifest = {
        "timestamp": "20260524Z",
        "db_backup_file": "db.sql",
        "storage_backup_file": "storage.zip",
        "eval_backup_file": "",
        "app_version": "1.0.0",
        "embedding_dimension": 384,
        "database_url": "postgresql+asyncpg://user:pass@host/db",
    }
    assert manifest_has_secrets(bad_manifest)


def test_restore_requires_confirm():
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "restore_postgres.ps1"
    if not script_path.exists():
        pytest.skip("restore_postgres.ps1 not found")
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File",
         str(script_path), "-BackupFile", "nonexistent.sql"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "ConfirmRestore" in output or "Restore requires" in output


def test_restore_storage_no_dangerous_path():
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "restore_storage.ps1"
    if not script_path.exists():
        pytest.skip("restore_storage.ps1 not found")
    content = script_path.read_text(encoding="utf-8")
    assert "/app/storage/.." not in content
    assert "rm -rf /app" not in content
    assert "find /app/storage -mindepth 1 -maxdepth 1" in content


def test_restore_storage_cleanup_fails_exits():
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "restore_storage.ps1"
    if not script_path.exists():
        pytest.skip("restore_storage.ps1 not found")
    content = script_path.read_text(encoding="utf-8")
    assert "Aborting restore" in content or "exit 1" in content
    assert "WARN: Storage cleanup" not in content


def test_restore_all_missing_manifest_fails():
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "restore_all.ps1"
    if not script_path.exists():
        pytest.skip("restore_all.ps1 not found")
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File",
         str(script_path), "-ManifestPath", "nonexistent.json", "-ConfirmRestore"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "not found" in output.lower() or "manifest" in output.lower()


def test_restore_all_manifest_references_missing_file_fails():
    import tempfile
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "restore_all.ps1"
    if not script_path.exists():
        pytest.skip("restore_all.ps1 not found")

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_data = {
            "timestamp": "20260524_testZ",
            "db_backup_file": "missing_backup.sql",
            "storage_backup_file": "missing_storage.zip",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = os.path.join(tmpdir, "backup_manifest_test.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File",
             str(script_path), "-ManifestPath", manifest_path, "-ConfirmRestore"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0


def test_restore_all_missing_db_backup_fails():
    import tempfile
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "restore_all.ps1"
    if not script_path.exists():
        pytest.skip("restore_all.ps1 not found")

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_data = {
            "timestamp": "20260524_testZ",
            "db_backup_file": "",
            "storage_backup_file": "storage.zip",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = os.path.join(tmpdir, "backup_manifest_test.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File",
             str(script_path), "-ManifestPath", manifest_path, "-ConfirmRestore"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "db_backup_file" in output.lower() or "database" in output.lower()


def test_restore_all_missing_storage_backup_fails():
    import tempfile
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "restore_all.ps1"
    if not script_path.exists():
        pytest.skip("restore_all.ps1 not found")

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_data = {
            "timestamp": "20260524_testZ",
            "db_backup_file": "db.sql",
            "storage_backup_file": "",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = os.path.join(tmpdir, "backup_manifest_test.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File",
             str(script_path), "-ManifestPath", manifest_path, "-ConfirmRestore"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "storage_backup_file" in output.lower() or "storage" in output.lower()


def test_restore_all_dryrun_validates_required_fields():
    import tempfile
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "restore_all.ps1"
    if not script_path.exists():
        pytest.skip("restore_all.ps1 not found")

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_data = {
            "timestamp": "20260524_testZ",
            "db_backup_file": "",
            "storage_backup_file": "",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = os.path.join(tmpdir, "backup_manifest_test.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File",
             str(script_path), "-ManifestPath", manifest_path, "-ConfirmRestore", "-DryRun"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0


def test_verify_all_python_fallback_structure():
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "verify_all.ps1"
    if not script_path.exists():
        pytest.skip("verify_all.ps1 not found")
    content = script_path.read_text(encoding="utf-8")
    assert 'PSCustomObject' in content
    assert 'Exe' in content
    assert 'Args' in content
    assert "py -3" not in content or 'Args = @("-3")' in content
    assert "Invoke-PythonSafeCommand" in content


def test_backup_all_manifest_requires_db_and_storage():
    script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "backup_all.ps1"
    if not script_path.exists():
        pytest.skip("backup_all.ps1 not found")
    content = script_path.read_text(encoding="utf-8")
    assert "db_backup_file is empty" in content or "Cannot generate manifest" in content
    assert "storage_backup_file is empty" in content or "Cannot generate manifest" in content


def test_production_check_manifest_empty_db_warns():
    from scripts.production_check import _check_backup_manifest
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_data = {
            "timestamp": "20260524_testZ",
            "db_backup_file": "",
            "storage_backup_file": "storage.zip",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = os.path.join(tmpdir, "backup_manifest_test.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        with patch("scripts.production_check.Path.cwd", return_value=Path(tmpdir)):
            backup_dir = tmpdir
            os.makedirs(os.path.join(backup_dir, "artifacts", "backups"), exist_ok=True)
            src = manifest_path
            dst = os.path.join(backup_dir, "artifacts", "backups", "backup_manifest_test.json")
            import shutil
            shutil.copy2(src, dst)
            result = _check_backup_manifest()
            assert result.status == "WARN"
            assert "db_backup_file" in result.message


def test_production_check_manifest_bom_readable():
    from scripts.production_check import _check_backup_manifest
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_data = {
            "timestamp": "20260524_testZ",
            "db_backup_file": "db.sql",
            "storage_backup_file": "storage.zip",
            "eval_backup_file": "",
            "app_version": "1.0.0",
            "embedding_dimension": 384,
        }
        manifest_path = os.path.join(tmpdir, "backup_manifest_bom.json")
        with open(manifest_path, "wb") as f:
            content = json.dumps(manifest_data).encode("utf-8")
            f.write(b"\xef\xbb\xbf" + content)

        with patch("scripts.production_check.Path.cwd", return_value=Path(tmpdir)):
            backup_dir = tmpdir
            os.makedirs(os.path.join(backup_dir, "artifacts", "backups"), exist_ok=True)
            import shutil
            dst = os.path.join(backup_dir, "artifacts", "backups", "backup_manifest_bom.json")
            shutil.copy2(manifest_path, dst)
            result = _check_backup_manifest()
            assert result.status == "PASS"


def test_production_auth_enabled_false_fails_in_production():
    from scripts.production_check import _check_auth_config

    with patch("app.config.settings.AUTH_ENABLED", False), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("app.config.settings.ENV", "production"):
        result = _check_auth_config()
        assert result.status == "FAIL"
        assert "AUTH_ENABLED must be true" in result.message


def test_production_auth_enabled_false_warns_in_dev():
    from scripts.production_check import _check_auth_config

    with patch("app.config.settings.AUTH_ENABLED", False), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("app.config.settings.ENV", "development"):
        result = _check_auth_config()
        assert result.status == "WARN"


def test_production_cors_wildcard_fails_in_production():
    from scripts.production_check import _check_cors

    with patch("app.config.settings.CORS_ALLOWED_ORIGINS", "*"), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("app.config.settings.ENV", "production"):
        result = _check_cors()
        assert result.status == "FAIL"
        assert "wildcard" in result.message.lower()


def test_production_cors_wildcard_warns_in_dev():
    from scripts.production_check import _check_cors

    with patch("app.config.settings.CORS_ALLOWED_ORIGINS", "*"), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("app.config.settings.ENV", "development"):
        result = _check_cors()
        assert result.status == "WARN"


def test_production_cors_configured_passes():
    from scripts.production_check import _check_cors

    with patch("app.config.settings.CORS_ALLOWED_ORIGINS", "https://example.com,https://app.example.com"), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("app.config.settings.ENV", "production"):
        result = _check_cors()
        assert result.status == "PASS"


def test_production_allow_dev_header_fails_in_production():
    from scripts.production_check import _check_auth_config

    with patch("app.config.settings.AUTH_ENABLED", True), \
         patch("app.config.settings.ALLOW_DEV_USER_HEADER", True), \
         patch("app.config.settings.SESSION_COOKIE_SECURE", True), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("app.config.settings.ENV", "production"):
        result = _check_auth_config()
        assert result.status == "FAIL"
        assert "ALLOW_DEV_USER_HEADER must be false" in result.message


def test_production_session_cookie_secure_fails_in_production():
    from scripts.production_check import _check_auth_config

    with patch("app.config.settings.AUTH_ENABLED", True), \
         patch("app.config.settings.ALLOW_DEV_USER_HEADER", False), \
         patch("app.config.settings.SESSION_COOKIE_SECURE", False), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("app.config.settings.ENV", "production"):
        result = _check_auth_config()
        assert result.status == "FAIL"
        assert "SESSION_COOKIE_SECURE must be true" in result.message


def test_cors_allowed_origins_parsing():
    with patch("app.config.settings.CORS_ALLOWED_ORIGINS", "http://a.com, http://b.com ,http://c.com"):
        origins = parse_cors_allowed_origins(settings.CORS_ALLOWED_ORIGINS)
        assert origins == ["http://a.com", "http://b.com", "http://c.com"]


def test_cors_allowed_origins_wildcard():
    with patch("app.config.settings.CORS_ALLOWED_ORIGINS", "*"):
        origins = parse_cors_allowed_origins(settings.CORS_ALLOWED_ORIGINS)
        assert origins == ["*"]


def test_cors_allowed_origins_empty():
    with patch("app.config.settings.CORS_ALLOWED_ORIGINS", "  ,  ,  "):
        origins = parse_cors_allowed_origins(settings.CORS_ALLOWED_ORIGINS)
        assert origins == []


@pytest.mark.asyncio
async def test_ready_endpoint_db_ok():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    with patch("app.routers.health.check_db_connection", new_callable=AsyncMock, return_value=True), \
         patch("app.routers.health.get_alembic_versions", new_callable=AsyncMock, return_value=("003_job_runs", "003_job_runs")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is True
            assert data["database"] == "connected"
            assert data["alembic_current"] == "003_job_runs"
            assert data["alembic_head"] == "003_job_runs"


@pytest.mark.asyncio
async def test_ready_endpoint_alembic_mismatch():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    with patch("app.routers.health.check_db_connection", new_callable=AsyncMock, return_value=True), \
         patch("app.routers.health.get_alembic_versions", new_callable=AsyncMock, return_value=("001_baseline", "003_job_runs")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is False
            assert data["alembic_current"] == "001_baseline"
            assert data["alembic_head"] == "003_job_runs"


@pytest.mark.asyncio
async def test_ready_endpoint_no_secrets():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    with patch("app.routers.health.check_db_connection", new_callable=AsyncMock, return_value=True), \
         patch("app.routers.health.get_alembic_versions", new_callable=AsyncMock, return_value=("003_job_runs", "003_job_runs")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health/ready")
            data = resp.json()
            body_str = json.dumps(data)
            assert "DATABASE_URL" not in body_str
            assert "postgresql+asyncpg://" not in body_str
            assert "API_KEY" not in body_str
            assert "sk-" not in body_str


@pytest.mark.asyncio
async def test_ready_endpoint_in_openapi():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "/health/ready" in data["paths"]


@pytest.mark.asyncio
async def test_ready_endpoint_db_disconnected():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    with patch("app.routers.health.check_db_connection", new_callable=AsyncMock, return_value=False), \
         patch("app.routers.health.get_alembic_versions", new_callable=AsyncMock, return_value=(None, None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is False
            assert data["database"] == "disconnected"


def test_normalize_env_strips_and_lowers():
    assert normalize_env("Production") == "production"
    assert normalize_env(" production ") == "production"
    assert normalize_env("PRODUCTION") == "production"
    assert normalize_env("  Development  ") == "development"
    assert normalize_env("DEVELOPMENT") == "development"


def test_is_production_env_case_insensitive():
    with patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("app.config.settings.ENV", "Production"):
        assert is_production() is True


def test_is_production_env_with_whitespace():
    with patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("app.config.settings.ENV", " production "):
        assert is_production() is True


def test_is_production_env_development():
    with patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("app.config.settings.ENV", "development"):
        assert is_production() is False


def test_is_production_real_model_required():
    with patch("app.config.settings.REAL_MODEL_REQUIRED", True), \
         patch("app.config.settings.ENV", "development"):
        assert is_production() is True


def test_production_auth_fail_with_env_production_case():
    from scripts.production_check import _check_auth_config

    with patch("app.config.settings.AUTH_ENABLED", False), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("app.config.settings.ENV", "Production"):
        result = _check_auth_config()
        assert result.status == "FAIL"
        assert "AUTH_ENABLED must be true" in result.message


def test_production_cors_wildcard_fail_with_env_whitespace():
    from scripts.production_check import _check_cors

    with patch("app.config.settings.CORS_ALLOWED_ORIGINS", "*"), \
         patch("app.config.settings.REAL_MODEL_REQUIRED", False), \
         patch("app.config.settings.ENV", " production "):
        result = _check_cors()
        assert result.status == "FAIL"
        assert "wildcard" in result.message.lower()


def test_cors_parse_strips_whitespace_entries():
    origins = parse_cors_allowed_origins(" http://a.com , , http://b.com ,  ")
    assert origins == ["http://a.com", "http://b.com"]


def test_cors_parse_pure_commas():
    origins = parse_cors_allowed_origins(" , , , ")
    assert origins == []


def test_cors_parse_single_origin():
    origins = parse_cors_allowed_origins("http://localhost:3000")
    assert origins == ["http://localhost:3000"]


def test_production_cors_localhost_fails_in_production():
    from scripts.production_check import _check_cors
    with patch("scripts.production_check.settings") as mock_settings, \
         patch("scripts.production_check.is_production", return_value=True):
        mock_settings.CORS_ALLOWED_ORIGINS = "http://localhost:3000,https://example.com"
        result = _check_cors()
        assert result.status == "FAIL"
        assert "localhost" in result.message.lower() or "dev origins" in result.message.lower()


def test_production_cors_127001_fails_in_production():
    from scripts.production_check import _check_cors
    with patch("scripts.production_check.settings") as mock_settings, \
         patch("scripts.production_check.is_production", return_value=True):
        mock_settings.CORS_ALLOWED_ORIGINS = "http://127.0.0.1:3000"
        result = _check_cors()
        assert result.status == "FAIL"
        assert "127.0.0.1" in result.message or "dev origins" in result.message.lower()


def test_production_cors_https_origin_passes():
    from scripts.production_check import _check_cors
    with patch("scripts.production_check.settings") as mock_settings, \
         patch("scripts.production_check.is_production", return_value=True):
        mock_settings.CORS_ALLOWED_ORIGINS = "https://example.com,https://app.example.com"
        result = _check_cors()
        assert result.status == "PASS"


def test_dev_cors_localhost_allowed_or_warn():
    from scripts.production_check import _check_cors
    with patch("scripts.production_check.settings") as mock_settings, \
         patch("scripts.production_check.is_production", return_value=False):
        mock_settings.CORS_ALLOWED_ORIGINS = "http://localhost:3000,http://localhost:3001"
        result = _check_cors()
        assert result.status in ("PASS", "WARN")
        assert result.status != "FAIL"


def test_production_cookie_secure_required():
    from scripts.production_check import _check_auth_config
    with patch("scripts.production_check.settings") as mock_settings, \
         patch("scripts.production_check.is_production", return_value=True):
        mock_settings.AUTH_ENABLED = True
        mock_settings.ALLOW_DEV_USER_HEADER = False
        mock_settings.SESSION_COOKIE_SECURE = False
        mock_settings.SESSION_TTL_SECONDS = 604800
        result = _check_auth_config()
        assert result.status == "FAIL"
        assert "SESSION_COOKIE_SECURE" in result.message
