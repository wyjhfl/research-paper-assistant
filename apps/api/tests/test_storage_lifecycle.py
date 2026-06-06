from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from tests.conftest import skip_if_no_db


def _make_mock_session(mock_session_cls, execute_return):
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_cls.return_value = mock_session
    mock_result = MagicMock()
    mock_result.all.return_value = execute_return
    mock_session.execute.return_value = mock_result
    return mock_session


@pytest.mark.asyncio
async def test_storage_audit_identifies_orphan():
    from scripts.storage_audit import run_audit

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        (storage / "referenced.pdf").write_bytes(b"hello")
        (storage / "orphan.pdf").write_bytes(b"world")

        with patch("scripts.storage_audit.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.storage_audit.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(str(storage / "referenced.pdf"), "referenced.pdf")])

            result = await run_audit()
            assert result["orphan_count"] >= 1
            assert any("orphan.pdf" in f for f in result["orphan_files"])


@pytest.mark.asyncio
async def test_storage_audit_identifies_missing():
    from scripts.storage_audit import run_audit

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)

        with patch("scripts.storage_audit.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.storage_audit.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(str(storage / "nonexistent.pdf"), "nonexistent.pdf")])

            result = await run_audit()
            assert result["missing_count"] >= 1


@pytest.mark.asyncio
async def test_storage_audit_missing_path_returns_all_fields():
    from scripts.storage_audit import run_audit

    with patch("scripts.storage_audit.settings.STORAGE_PATH", "/nonexistent/path/that/does/not/exist"):
        result = await run_audit()

    assert result["storage_path_exists"] is False
    assert result["total_files"] == 0
    assert result["total_bytes"] == 0
    assert result["orphan_files"] == []
    assert result["orphan_count"] == 0
    assert result["orphan_bytes"] == 0
    assert result["missing_files"] == []
    assert result["missing_count"] == 0


@pytest.mark.asyncio
async def test_storage_audit_is_read_only():
    from scripts.storage_audit import run_audit

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        (storage / "orphan.pdf").write_bytes(b"orphan data")

        with patch("scripts.storage_audit.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.storage_audit.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_audit()
            assert result["orphan_count"] >= 1
            assert (storage / "orphan.pdf").exists()
            assert (storage / "orphan.pdf").read_bytes() == b"orphan data"


@pytest.mark.asyncio
async def test_storage_audit_no_absolute_paths():
    from scripts.storage_audit import run_audit

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        (storage / "file.pdf").write_bytes(b"data")

        with patch("scripts.storage_audit.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.storage_audit.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(str(storage / "file.pdf"), "file.pdf")])

            result = await run_audit()
            output = json.dumps(result)
            assert tmpdir not in output
            assert str(storage) not in output


@pytest.mark.asyncio
async def test_cleanup_storage_dry_run_no_delete():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        orphan_file = storage / "orphan.pdf"
        orphan_file.write_bytes(b"world")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=True)
            assert result["dry_run"] is True
            assert result["deleted_count"] == 0
            assert result["candidate_count"] >= 1
            assert orphan_file.exists()


@pytest.mark.asyncio
async def test_cleanup_storage_confirm_deletes_orphan():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        orphan_file = storage / "orphan.pdf"
        referenced_file = storage / "referenced.pdf"
        orphan_file.write_bytes(b"world")
        referenced_file.write_bytes(b"hello")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(str(referenced_file),)])

            result = await run_cleanup(dry_run=False)
            assert result["dry_run"] is False
            assert result["deleted_count"] >= 1
            assert not orphan_file.exists()
            assert referenced_file.exists()


@pytest.mark.asyncio
async def test_cleanup_storage_referenced_not_deleted():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        ref_file = storage / "important.pdf"
        ref_file.write_bytes(b"important data")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(str(ref_file),)])

            result = await run_cleanup(dry_run=False)
            assert result["deleted_count"] == 0
            assert ref_file.exists()
            assert ref_file.read_bytes() == b"important data"


@pytest.mark.asyncio
async def test_cleanup_storage_symlink_skipped():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        external_dir = Path(tmpdir + "_external")
        external_dir.mkdir()
        external_file = external_dir / "secret.pdf"
        external_file.write_bytes(b"secret data")

        symlink_path = storage / "link.pdf"
        try:
            symlink_path.symlink_to(external_file)
        except OSError:
            pytest.skip("symlink not supported on this platform")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=False)
            assert result["skipped_symlink"] >= 1
            assert external_file.exists()
            assert external_file.read_bytes() == b"secret data"


@pytest.mark.asyncio
async def test_cleanup_storage_path_traversal():
    from scripts.cleanup_storage import _is_within_storage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        assert _is_within_storage(Path("../../etc/passwd"), storage) is False


@pytest.mark.asyncio
async def test_cleanup_storage_sibling_prefix_blocked():
    from scripts.cleanup_storage import _is_within_storage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        evil = Path(tmpdir + "_evil") / "file.pdf"
        assert _is_within_storage(evil, storage) is False


@pytest.mark.asyncio
async def test_cleanup_storage_path_violation_candidate_skipped():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls, \
             patch("scripts.cleanup_storage._is_within_storage", return_value=False):
            _make_mock_session(mock_session_cls, [])

            (storage / "trapped.pdf").write_bytes(b"x")
            result = await run_cleanup(dry_run=True)
            assert result["skipped_path_violation"] >= 1
            assert result["candidate_count"] == 0


@pytest.mark.asyncio
async def test_cleanup_storage_missing_path_returns_safe_json():
    from scripts.cleanup_storage import run_cleanup

    with patch("scripts.cleanup_storage.settings.STORAGE_PATH", "/nonexistent/path/that/does/not/exist"):
        result = await run_cleanup(dry_run=True)

    assert result["storage_path_exists"] is False
    assert result["orphan_count"] == 0
    assert result["candidate_count"] == 0
    assert result["deleted_count"] == 0
    assert result["skipped_path_violation"] == 0
    assert result["skipped_symlink"] == 0
    assert result["error_count"] == 0
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_cleanup_storage_no_absolute_paths_in_output():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        (storage / "orphan.pdf").write_bytes(b"data")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=True)
            output = json.dumps(result)
            assert tmpdir not in output
            assert str(storage) not in output
            for f in result.get("candidate_files", []):
                assert not Path(f).is_absolute()


@pytest.mark.asyncio
async def test_cleanup_storage_dry_run_candidate_preview():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        for i in range(5):
            (storage / f"orphan_{i:03d}.pdf").write_bytes(b"x")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=True, preview_limit=3)
            assert result["candidate_count"] == 5
            assert len(result["candidate_files"]) == 3
            assert result["preview_truncated"] is True


@pytest.mark.asyncio
async def test_cleanup_storage_dry_run_preview_not_truncated():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        (storage / "orphan.pdf").write_bytes(b"data")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=True, preview_limit=100)
            assert result["preview_truncated"] is False
            assert len(result["candidate_files"]) == 1


@pytest.mark.asyncio
async def test_cleanup_storage_delete_error_recorded():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        (storage / "orphan.pdf").write_bytes(b"data")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls, \
             patch("scripts.cleanup_storage.Path.unlink", side_effect=OSError("permission denied")):
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=False)
            assert result["error_count"] >= 1
            assert len(result["errors"]) >= 1
            assert "orphan.pdf" in result["errors"][0]
            assert tmpdir not in result["errors"][0]


@pytest.mark.asyncio
async def test_cleanup_storage_limit_parameter():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        for i in range(5):
            (storage / f"orphan_{i:03d}.pdf").write_bytes(b"x")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=True, limit=2)
            assert result["orphan_count"] == 5
            assert result["candidate_count"] == 2


@pytest.mark.asyncio
async def test_cleanup_storage_confirm_limit_parameter():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        for i in range(5):
            (storage / f"orphan_{i:03d}.pdf").write_bytes(b"x")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=False, limit=2)
            assert result["orphan_count"] == 5
            assert result["deleted_count"] == 2
            remaining = list(storage.glob("orphan_*.pdf"))
            assert len(remaining) == 3


@pytest.mark.asyncio
async def test_cleanup_storage_does_not_delete_directories():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        sub_dir = storage / "subdir"
        sub_dir.mkdir()

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [])

            result = await run_cleanup(dry_run=False)
            assert sub_dir.exists()
            assert result["deleted_count"] == 0


@pytest.mark.asyncio
async def test_cleanup_jobs_dry_run_no_delete():
    from scripts.cleanup_jobs import run_cleanup

    with patch("scripts.cleanup_jobs.async_session") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5
        mock_session.execute.return_value = mock_count_result

        result = await run_cleanup(dry_run=True, retention_days=30)
        assert result["dry_run"] is True
        assert result["eligible_count"] == 5
        assert result["deleted_count"] == 0
        mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_jobs_confirm_deletes_terminal():
    from scripts.cleanup_jobs import run_cleanup

    with patch("scripts.cleanup_jobs.async_session") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3

        mock_del_result = MagicMock()
        mock_del_result.rowcount = 3

        mock_session.execute.side_effect = [mock_count_result, mock_del_result]

        result = await run_cleanup(dry_run=False, retention_days=30)
        assert result["deleted_count"] == 3
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_jobs_retention_days_zero_rejected():
    from scripts.cleanup_jobs import run_cleanup, RetentionDaysError

    with pytest.raises(RetentionDaysError):
        await run_cleanup(dry_run=True, retention_days=0)


@pytest.mark.asyncio
async def test_cleanup_jobs_retention_days_negative_rejected():
    from scripts.cleanup_jobs import run_cleanup, RetentionDaysError

    with pytest.raises(RetentionDaysError):
        await run_cleanup(dry_run=True, retention_days=-1)


@pytest.mark.asyncio
async def test_storage_summary_user_isolation():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp_a = await client.get(
            "/usage/storage-summary",
            headers={"X-User-Id": "user_isolation_a"},
        )
        assert resp_a.status_code == 200
        data_a = resp_a.json()

        resp_b = await client.get(
            "/usage/storage-summary",
            headers={"X-User-Id": "user_isolation_b"},
        )
        assert resp_b.status_code == 200
        data_b = resp_b.json()

        assert "paper_count" in data_a
        assert "paper_count" in data_b


@pytest.mark.asyncio
async def test_storage_summary_strict_user_isolation():
    from app.routers.usage import storage_summary

    def _make_result(scalar_val, scalars_val=None):
        result = MagicMock()
        result.scalar.return_value = scalar_val
        if scalars_val is not None:
            result.scalars.return_value = MagicMock(all=MagicMock(return_value=scalars_val))
        return result

    async def _call_for_user(uid, paper_count, chunk_count, failed_count, file_paths):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[
            _make_result(paper_count),
            _make_result(chunk_count),
            _make_result(failed_count),
            _make_result(0, file_paths),
        ])
        return await storage_summary(db=mock_db, user_id=uid)

    result_a = await _call_for_user("user_strict_a", paper_count=3, chunk_count=10, failed_count=0, file_paths=[])
    result_b = await _call_for_user("user_strict_b", paper_count=7, chunk_count=25, failed_count=1, file_paths=[])

    assert result_a.paper_count == 3
    assert result_a.chunk_count == 10
    assert result_a.failed_paper_count == 0
    assert result_b.paper_count == 7
    assert result_b.chunk_count == 25
    assert result_b.failed_paper_count == 1


@pytest.mark.asyncio
async def test_storage_summary_storage_path_boundary():
    from app.routers.usage import storage_summary

    with tempfile.TemporaryDirectory() as tmpdir:
        storage_root = Path(tmpdir)
        inside_file = storage_root / "inside.pdf"
        inside_file.write_bytes(b"a" * 100)

        external_dir = Path(tmpdir + "_external")
        external_dir.mkdir()
        external_file = external_dir / "outside.pdf"
        external_file.write_bytes(b"b" * 999)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar=MagicMock(return_value=2),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[str(inside_file), str(external_file)])))
        ))

        with patch("app.routers.usage.settings.STORAGE_PATH", tmpdir):
            result = await storage_summary(db=mock_db, user_id="boundary_test_user")

        assert result.storage_bytes == 100


@pytest.mark.asyncio
async def test_storage_summary_no_absolute_path():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/usage/storage-summary",
            headers={"X-User-Id": "default"},
        )
        assert resp.status_code == 200
        data = resp.json()
        body_str = json.dumps(data)
        assert "file_path" not in body_str
        assert "STORAGE_PATH" not in body_str
        assert "paper_count" in data
        assert "chunk_count" in data
        assert "storage_bytes" in data
        assert "failed_paper_count" in data


@pytest.mark.asyncio
async def test_storage_summary_in_openapi():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "/usage/storage-summary" in data["paths"]


def test_maintenance_scripts_check():
    from scripts.production_check import _check_maintenance_scripts
    result = _check_maintenance_scripts()
    assert result.status == "PASS"
    assert "all present" in result.message


def test_ops_check_no_cleanup_confirm():
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    ops_check = project_root / "scripts" / "ops_check.ps1"
    if not ops_check.exists():
        pytest.skip("ops_check.ps1 not found")
    content = ops_check.read_text()
    assert "cleanup_storage.py --confirm" not in content
    assert "--confirm" not in content


@pytest.mark.asyncio
@skip_if_no_db()
async def test_paper_repository_chunk_helpers_filter_user_id():
    from app.models import Paper, PaperChunk
    from app.repositories.paper_repo import PaperRepository
    from tests.conftest import _test_session_factory

    async with _test_session_factory() as session:
        own = Paper(title="own", filename="own.pdf", file_path="own.pdf", status="completed", user_id="user_a")
        other = Paper(title="other", filename="other.pdf", file_path="other.pdf", status="completed", user_id="user_b")
        session.add_all([own, other])
        await session.flush()
        session.add(PaperChunk(paper_id=own.id, chunk_index=0, text="own", embedding=[0.1] * 384))
        session.add(PaperChunk(paper_id=other.id, chunk_index=0, text="other", embedding=[0.2] * 384))
        await session.commit()

        repo = PaperRepository(session)
        assert await repo.get_chunk_count(own.id, user_id="user_a") == 1
        assert await repo.get_chunk_count(own.id, user_id="user_b") == 0
        assert await repo.get_embedding_count(other.id, user_id="user_a") == 0
        assert await repo.get_chunks_by_paper(other.id, user_id="user_a") == []
        assert await repo.clear_embeddings(other.id, user_id="user_a") == 0
        assert await repo.get_embedding_count(other.id, user_id="user_b") == 1


def test_ops_check_storage_audit_parses_json_counts():
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    ops_check = project_root / "scripts" / "ops_check.ps1"
    if not ops_check.exists():
        pytest.skip("ops_check.ps1 not found")
    content = ops_check.read_text(encoding="utf-8")
    assert "ConvertFrom-Json" in content, "ops_check.ps1 must parse storage_audit JSON"
    assert "missing_count" in content, "storage missing files must be inspected"
    assert "orphan_count" in content, "storage orphan files must be inspected"
    assert "storage_audit missing files" in content, "missing storage files must fail ops_check"
    assert "storage orphan_count > 0" in content, "orphan storage files must warn"


def test_production_check_no_cleanup_confirm():
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    prod_check = project_root / "apps" / "api" / "scripts" / "production_check.py"
    if not prod_check.exists():
        pytest.skip("production_check.py not found")
    content = prod_check.read_text()
    assert "cleanup_storage.py --confirm" not in content
    assert "cleanup_storage" not in content or "--confirm" not in content


@pytest.mark.asyncio
async def test_cleanup_storage_absolute_file_path_referenced():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()
        uploads_dir = storage / "uploads" / "default"
        uploads_dir.mkdir(parents=True)
        ref_file = uploads_dir / "ref.pdf"
        ref_file.write_bytes(b"referenced")
        orphan_file = storage / "orphan.pdf"
        orphan_file.write_bytes(b"orphan")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", str(storage)), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(str(ref_file),)])

            result = await run_cleanup(dry_run=False)
            assert ref_file.exists()
            assert not orphan_file.exists()
            assert result["deleted_count"] == 1


@pytest.mark.asyncio
async def test_cleanup_storage_relative_file_path_with_storage_prefix():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()
        uploads_dir = storage / "uploads" / "default"
        uploads_dir.mkdir(parents=True)
        ref_file = uploads_dir / "ref.pdf"
        ref_file.write_bytes(b"referenced")
        orphan_file = storage / "orphan.pdf"
        orphan_file.write_bytes(b"orphan")

        relative_path = "storage/uploads/default/ref.pdf"

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", str(storage)), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(relative_path,)])

            result = await run_cleanup(dry_run=False)
            assert ref_file.exists(), "referenced file with storage/ prefix should not be deleted"
            assert not orphan_file.exists()
            assert result["deleted_count"] == 1


@pytest.mark.asyncio
async def test_cleanup_storage_relative_file_path_without_storage_prefix():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()
        uploads_dir = storage / "uploads" / "default"
        uploads_dir.mkdir(parents=True)
        ref_file = uploads_dir / "ref.pdf"
        ref_file.write_bytes(b"referenced")
        orphan_file = storage / "orphan.pdf"
        orphan_file.write_bytes(b"orphan")

        relative_path = "uploads/default/ref.pdf"

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", str(storage)), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(relative_path,)])

            result = await run_cleanup(dry_run=False)
            assert ref_file.exists(), "referenced file without storage/ prefix should not be deleted"
            assert not orphan_file.exists()
            assert result["deleted_count"] == 1


@pytest.mark.asyncio
async def test_storage_audit_relative_file_path_not_orphan():
    from scripts.storage_audit import run_audit

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()
        uploads_dir = storage / "uploads" / "default"
        uploads_dir.mkdir(parents=True)
        ref_file = uploads_dir / "ref.pdf"
        ref_file.write_bytes(b"referenced")

        relative_path = "uploads/default/ref.pdf"

        with patch("scripts.storage_audit.settings.STORAGE_PATH", str(storage)), \
             patch("scripts.storage_audit.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(relative_path, "ref.pdf")])

            result = await run_audit()
            assert result["orphan_count"] == 0, "file referenced by relative path should not be orphan"


@pytest.mark.asyncio
async def test_storage_audit_relative_file_path_with_storage_prefix_not_orphan():
    from scripts.storage_audit import run_audit

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()
        uploads_dir = storage / "uploads" / "default"
        uploads_dir.mkdir(parents=True)
        ref_file = uploads_dir / "ref.pdf"
        ref_file.write_bytes(b"referenced")

        relative_path = "storage/uploads/default/ref.pdf"

        with patch("scripts.storage_audit.settings.STORAGE_PATH", str(storage)), \
             patch("scripts.storage_audit.async_session") as mock_session_cls:
            _make_mock_session(mock_session_cls, [(relative_path, "ref.pdf")])

            result = await run_audit()
            assert result["orphan_count"] == 0, "file referenced by storage/ prefix path should not be orphan"


@pytest.mark.asyncio
async def test_cleanup_storage_external_path_returns_none():
    from scripts.cleanup_storage import _referenced_rel_path

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()

        external_dir = Path(tmpdir) / "external"
        external_dir.mkdir()
        external_file = external_dir / "file.pdf"
        external_file.write_bytes(b"x")

        result = _referenced_rel_path(str(external_file), storage)
        assert result is None


def test_referenced_rel_path_absolute_within_storage():
    from scripts.cleanup_storage import _referenced_rel_path

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()
        uploads_dir = storage / "uploads" / "default"
        uploads_dir.mkdir(parents=True)
        ref_file = uploads_dir / "ref.pdf"
        ref_file.write_bytes(b"x")

        result = _referenced_rel_path(str(ref_file), storage)
        assert result is not None
        assert result == "uploads/default/ref.pdf"
        assert not Path(result).is_absolute()


def test_referenced_rel_path_relative_with_storage_prefix():
    from scripts.cleanup_storage import _referenced_rel_path

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()

        result = _referenced_rel_path("storage/uploads/default/ref.pdf", storage)
        assert result is not None
        assert result == "uploads/default/ref.pdf"


def test_referenced_rel_path_relative_without_storage_prefix():
    from scripts.cleanup_storage import _referenced_rel_path

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()

        result = _referenced_rel_path("uploads/default/ref.pdf", storage)
        assert result is not None
        assert result == "uploads/default/ref.pdf"


def test_referenced_rel_path_external_absolute():
    from scripts.cleanup_storage import _referenced_rel_path

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()

        external_dir = Path(tmpdir) / "external"
        external_dir.mkdir()
        external_file = external_dir / "file.pdf"
        external_file.write_bytes(b"x")

        result = _referenced_rel_path(str(external_file), storage)
        assert result is None


def test_referenced_rel_path_no_absolute_paths_in_output():
    from scripts.cleanup_storage import _referenced_rel_path

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "storage"
        storage.mkdir()
        uploads_dir = storage / "uploads" / "default"
        uploads_dir.mkdir(parents=True)
        ref_file = uploads_dir / "ref.pdf"
        ref_file.write_bytes(b"x")

        result = _referenced_rel_path(str(ref_file), storage)
        assert result is not None
        assert not Path(result).is_absolute()
        assert str(storage) not in result
