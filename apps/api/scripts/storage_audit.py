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


async def run_audit() -> dict:
    storage_path = Path(settings.STORAGE_PATH)
    if not storage_path.exists():
        return {
            "storage_path_exists": False,
            "total_files": 0,
            "total_bytes": 0,
            "orphan_files": [],
            "orphan_count": 0,
            "orphan_bytes": 0,
            "missing_files": [],
            "missing_count": 0,
        }

    all_files: dict[str, int] = {}
    for root, _dirs, files in os.walk(storage_path):
        for f in files:
            fp = Path(root) / f
            try:
                size = fp.stat().st_size
            except OSError:
                size = 0
            rel = str(fp.relative_to(storage_path))
            all_files[rel] = size

    async with async_session() as session:
        result = await session.execute(select(Paper.file_path, Paper.filename))
        db_entries = result.all()

    referenced_rels: set[str] = set()
    missing_files: list[str] = []
    for file_path, filename in db_entries:
        try:
            rel = str(Path(file_path).relative_to(storage_path))
        except ValueError:
            rel = str(Path(file_path).name)
        referenced_rels.add(rel)
        if rel not in all_files and not Path(file_path).exists():
            missing_files.append(filename or rel)

    orphan_files = [rel for rel in all_files if rel not in referenced_rels]

    return {
        "storage_path_exists": True,
        "total_files": len(all_files),
        "total_bytes": sum(all_files.values()),
        "orphan_files": sorted(orphan_files),
        "orphan_count": len(orphan_files),
        "orphan_bytes": sum(all_files.get(f, 0) for f in orphan_files),
        "missing_files": sorted(missing_files),
        "missing_count": len(missing_files),
    }


async def main():
    result = await run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    asyncio.run(main())
