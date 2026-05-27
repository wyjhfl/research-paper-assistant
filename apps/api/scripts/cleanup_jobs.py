from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, delete, func

from app.database import async_session
from app.models import JobRun


class RetentionDaysError(ValueError):
    pass


async def run_cleanup(dry_run: bool = True, retention_days: int = 30, user_id: str | None = None) -> dict:
    if retention_days < 1:
        raise RetentionDaysError(f"retention_days must be >= 1, got {retention_days}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    terminal_statuses = ("completed", "cancelled", "failed")

    async with async_session() as session:
        count_stmt = (
            select(func.count())
            .select_from(JobRun)
            .where(
                JobRun.status.in_(terminal_statuses),
                JobRun.finished_at < cutoff,
            )
        )
        if user_id:
            count_stmt = count_stmt.where(JobRun.user_id == user_id)

        total_eligible = (await session.execute(count_stmt)).scalar() or 0

        if dry_run:
            return {
                "dry_run": True,
                "retention_days": retention_days,
                "user_id": user_id,
                "eligible_count": total_eligible,
                "deleted_count": 0,
            }

        del_stmt = (
            delete(JobRun)
            .where(
                JobRun.status.in_(terminal_statuses),
                JobRun.finished_at < cutoff,
            )
        )
        if user_id:
            del_stmt = del_stmt.where(JobRun.user_id == user_id)

        result = await session.execute(del_stmt)
        deleted_count = result.rowcount
        await session.commit()

        return {
            "dry_run": False,
            "retention_days": retention_days,
            "user_id": user_id,
            "eligible_count": total_eligible,
            "deleted_count": deleted_count,
        }


def _parse_args():
    dry_run = True
    retention_days = 30
    user_id = None

    for arg in sys.argv[1:]:
        if arg == "--confirm":
            dry_run = False
        elif arg.startswith("--retention-days="):
            try:
                retention_days = int(arg.split("=", 1)[1])
            except ValueError:
                print(f"ERROR: invalid --retention-days value: {arg}", file=sys.stderr)
                sys.exit(1)
        elif arg.startswith("--user-id="):
            user_id = arg.split("=", 1)[1]

    return dry_run, retention_days, user_id


async def main():
    dry_run, retention_days, user_id = _parse_args()
    try:
        result = await run_cleanup(dry_run=dry_run, retention_days=retention_days, user_id=user_id)
    except RetentionDaysError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    asyncio.run(main())
