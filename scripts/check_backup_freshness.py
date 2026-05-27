import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "docker-compose.yml").exists() or (current / ".env.example").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Check backup freshness")
    parser.add_argument("--max-age-hours", type=float, default=24, help="Max age in hours (default: 24)")
    parser.add_argument("--backups-dir", type=str, default=None, help="Backups directory (default: auto-detect)")
    args = parser.parse_args()

    project_root = _find_project_root()
    backups_dir = Path(args.backups_dir) if args.backups_dir else project_root / "artifacts" / "backups"

    manifests = sorted(backups_dir.glob("backup_manifest_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

    now = datetime.now(timezone.utc)

    if not manifests:
        result = {
            "ok": False,
            "latest_manifest": None,
            "age_hours": None,
            "max_age_hours": args.max_age_hours,
            "warnings": ["No backup manifest found"],
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    latest = manifests[0]
    latest_name = latest.name

    try:
        data = json.loads(latest.read_text())
        ts_str = data.get("timestamp", "")
        if ts_str:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            ts = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
    except (json.JSONDecodeError, ValueError):
        ts = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)

    age_hours = (now - ts).total_seconds() / 3600

    warnings = []
    if age_hours > args.max_age_hours:
        warnings.append(f"Backup is {age_hours:.1f}h old, exceeds max {args.max_age_hours}h")

    ok = age_hours <= args.max_age_hours

    result = {
        "ok": ok,
        "latest_manifest": latest_name,
        "age_hours": round(age_hours, 1),
        "max_age_hours": args.max_age_hours,
        "warnings": warnings,
    }

    print(json.dumps(result, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
