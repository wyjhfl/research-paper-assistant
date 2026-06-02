from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Paper


def _is_within_storage(target: Path, storage_root: Path) -> bool:
    storage_root = storage_root.resolve()
    try:
        target.resolve().relative_to(storage_root)
        return True
    except ValueError:
        return False


def _safe_rel_path(target: Path, storage_root: Path) -> str | None:
    try:
        return str(target.relative_to(storage_root)).replace("\\", "/")
    except ValueError:
        return None


def _referenced_rel_path(file_path: str, storage_root: Path) -> str | None:
    resolved_root = storage_root.resolve()
    p = Path(file_path)

    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(resolved_root)).replace("\\", "/")
        except ValueError:
            return None

    resolved_cwd = Path.cwd().resolve()
    candidate = (resolved_cwd / p).resolve()
    try:
        return str(candidate.relative_to(resolved_root)).replace("\\", "/")
    except ValueError:
        pass

    parts = p.parts
    if parts and parts[0] == resolved_root.name:
        stripped = Path(*parts[1:])
        if stripped.parts:
            return str(stripped).replace("\\", "/")

    if not p.is_absolute():
        return str(p).replace("\\", "/")

    return None


async def run_cleanup(
    dry_run: bool = True,
    limit: int = 0,
    preview_limit: int = 100,
) -> dict:
    storage_path = Path(settings.STORAGE_PATH).resolve()
    if not storage_path.exists():
        return {
            "dry_run": dry_run,
            "storage_path_exists": False,
            "orphan_count": 0,
            "candidate_count": 0,
            "candidate_bytes": 0,
            "deleted_count": 0,
            "deleted_bytes": 0,
            "skipped_path_violation": 0,
            "skipped_symlink": 0,
            "error_count": 0,
            "errors": [],
            "candidate_files": [],
            "preview_truncated": False,
        }

    all_files: dict[str, int] = {}
    for root, _dirs, files in os.walk(storage_path, followlinks=False):
        for f in files:
            fp = Path(root) / f
            try:
                size = fp.stat(follow_symlinks=False).st_size
            except OSError:
                size = 0
            rel = _safe_rel_path(fp, storage_path)
            if rel is not None:
                all_files[rel] = size

    async with async_session() as session:
        result = await session.execute(select(Paper.file_path))
        db_paths = result.all()

    referenced_rels: set[str] = set()
    for (file_path,) in db_paths:
        rel = _referenced_rel_path(file_path, storage_path)
        if rel is not None:
            referenced_rels.add(rel)

    orphan_files = [rel for rel in sorted(all_files.keys()) if rel not in referenced_rels]

    all_orphan_count = len(orphan_files)

    if limit > 0:
        orphan_files = orphan_files[:limit]

    candidate_count = 0
    candidate_bytes = 0
    deleted_count = 0
    deleted_bytes = 0
    skipped_path_violation = 0
    skipped_symlink = 0
    error_count = 0
    errors: list[str] = []
    candidate_files: list[str] = []

    for rel in orphan_files:
        target = storage_path / rel

        if target.is_symlink():
            skipped_symlink += 1
            continue

        if not _is_within_storage(target, storage_path):
            skipped_path_violation += 1
            continue

        if not target.is_file():
            continue

        if dry_run:
            candidate_count += 1
            candidate_bytes += all_files.get(rel, 0)
            candidate_files.append(rel)
        else:
            try:
                size = target.stat(follow_symlinks=False).st_size
                target.unlink()
                deleted_count += 1
                deleted_bytes += size
            except OSError as e:
                error_count += 1
                safe_name = Path(rel).name
                errors.append(f"failed to delete {safe_name}: {type(e).__name__}")

    preview_truncated = False
    if dry_run and len(candidate_files) > preview_limit:
        candidate_files = candidate_files[:preview_limit]
        preview_truncated = True

    result_data: dict = {
        "dry_run": dry_run,
        "storage_path_exists": True,
        "orphan_count": all_orphan_count,
    }

    if dry_run:
        result_data["candidate_count"] = candidate_count
        result_data["candidate_bytes"] = candidate_bytes
        result_data["candidate_files"] = candidate_files
        result_data["preview_truncated"] = preview_truncated
        result_data["deleted_count"] = 0
        result_data["deleted_bytes"] = 0
    else:
        result_data["candidate_count"] = 0
        result_data["candidate_bytes"] = 0
        result_data["deleted_count"] = deleted_count
        result_data["deleted_bytes"] = deleted_bytes

    result_data["skipped_path_violation"] = skipped_path_violation
    result_data["skipped_symlink"] = skipped_symlink
    result_data["error_count"] = error_count
    result_data["errors"] = errors

    return result_data


def parse_args():
    parser = argparse.ArgumentParser(description="Storage orphan cleanup")
    parser.add_argument("--confirm", action="store_true", help="Actually delete orphan files (default: dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="Max number of files to process (0=unlimited)")
    parser.add_argument("--preview-limit", type=int, default=100, help="Max candidate files in dry-run output")
    return parser.parse_args()


async def main():
    args = parse_args()
    result = await run_cleanup(
        dry_run=not args.confirm,
        limit=args.limit,
        preview_limit=args.preview_limit,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    asyncio.run(main())
