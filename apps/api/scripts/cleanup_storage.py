from __future__ import annotations

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


async def run_cleanup(dry_run: bool = True) -> dict:
    storage_path = Path(settings.STORAGE_PATH).resolve()
    if not storage_path.exists():
        return {
            "storage_path_exists": False,
            "orphan_count": 0,
            "deleted_count": 0,
            "deleted_bytes": 0,
            "skipped_path_violation": 0,
            "skipped_symlink": 0,
        }

    all_files: dict[str, int] = {}
    for root, _dirs, files in os.walk(storage_path, followlinks=False):
        for f in files:
            fp = Path(root) / f
            try:
                size = fp.stat(follow_symlinks=False).st_size
            except OSError:
                size = 0
            rel = str(fp.relative_to(storage_path))
            all_files[rel] = size

    async with async_session() as session:
        result = await session.execute(select(Paper.file_path))
        db_paths = result.all()

    referenced_rels: set[str] = set()
    for (file_path,) in db_paths:
        try:
            rel = str(Path(file_path).relative_to(storage_path))
        except ValueError:
            rel = str(Path(file_path).name)
        referenced_rels.add(rel)

    orphan_files = [rel for rel in all_files if rel not in referenced_rels]

    deleted_count = 0
    deleted_bytes = 0
    skipped_path_violation = 0
    skipped_symlink = 0

    for rel in orphan_files:
        target = storage_path / rel

        if target.is_symlink():
            skipped_symlink += 1
            continue

        if not _is_within_storage(target, storage_path):
            skipped_path_violation += 1
            continue

        if dry_run:
            deleted_count += 1
            deleted_bytes += all_files.get(rel, 0)
        else:
            try:
                size = target.stat(follow_symlinks=False).st_size
                target.unlink()
                deleted_count += 1
                deleted_bytes += size
            except OSError:
                pass

    return {
        "dry_run": dry_run,
        "orphan_count": len(orphan_files),
        "deleted_count": deleted_count,
        "deleted_bytes": deleted_bytes,
        "skipped_path_violation": skipped_path_violation,
        "skipped_symlink": skipped_symlink,
    }


async def main():
    confirm = "--confirm" in sys.argv
    result = await run_cleanup(dry_run=not confirm)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    asyncio.run(main())
