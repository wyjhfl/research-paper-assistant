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


@pytest.mark.asyncio
async def test_storage_audit_identifies_orphan():
    from scripts.storage_audit import run_audit

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        (storage / "referenced.pdf").write_bytes(b"hello")
        (storage / "orphan.pdf").write_bytes(b"world")

        with patch("scripts.storage_audit.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.storage_audit.async_session") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_result = MagicMock()
            mock_result.all.return_value = [(str(storage / "referenced.pdf"), "referenced.pdf")]
            mock_session.execute.return_value = mock_result

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
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_result = MagicMock()
            mock_result.all.return_value = [(str(storage / "nonexistent.pdf"), "nonexistent.pdf")]
            mock_session.execute.return_value = mock_result

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
async def test_cleanup_storage_dry_run_no_delete():
    from scripts.cleanup_storage import run_cleanup

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        orphan_file = storage / "orphan.pdf"
        orphan_file.write_bytes(b"world")

        with patch("scripts.cleanup_storage.settings.STORAGE_PATH", tmpdir), \
             patch("scripts.cleanup_storage.async_session") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_session.execute.return_value = mock_result

            result = await run_cleanup(dry_run=True)
            assert result["dry_run"] is True
            assert result["deleted_count"] >= 1
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
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_result = MagicMock()
            mock_result.all.return_value = [(str(referenced_file),)]
            mock_session.execute.return_value = mock_result

            result = await run_cleanup(dry_run=False)
            assert not orphan_file.exists()
            assert referenced_file.exists()


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
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_session.execute.return_value = mock_result

            result = await run_cleanup(dry_run=False)
            assert result["skipped_symlink"] >= 1
            assert external_file.exists()
            assert external_file.read_bytes() == b"secret data"


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
