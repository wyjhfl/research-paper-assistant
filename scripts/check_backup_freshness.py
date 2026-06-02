import argparse
import json
import re
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


def _try_parse_timestamp(ts_str: str):
    if not ts_str:
        return None

    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt
    except ValueError:
        pass

    compact_z = re.match(r"^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})Z$", ts_str)
    if compact_z:
        return datetime(
            int(compact_z.group(1)), int(compact_z.group(2)), int(compact_z.group(3)),
            int(compact_z.group(4)), int(compact_z.group(5)), int(compact_z.group(6)),
            tzinfo=timezone.utc,
        )

    compact_noz = re.match(r"^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$", ts_str)
    if compact_noz:
        return datetime(
            int(compact_noz.group(1)), int(compact_noz.group(2)), int(compact_noz.group(3)),
            int(compact_noz.group(4)), int(compact_noz.group(5)), int(compact_noz.group(6)),
            tzinfo=timezone.utc,
        )

    return None


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _load_manifest_candidate(path: Path):
    name = path.name
    fallback_mtime = path.stat().st_mtime
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, name

    ts_str = data.get("timestamp", "")
    parsed = _try_parse_timestamp(ts_str)

    if parsed is not None:
        parsed = _ensure_aware(parsed)
        return {
            "path": path,
            "name": name,
            "timestamp_dt": parsed,
            "timestamp_source": "manifest",
        }, None

    ts = datetime.fromtimestamp(fallback_mtime, tz=timezone.utc)
    return {
        "path": path,
        "name": name,
        "timestamp_dt": ts,
        "timestamp_source": "mtime_fallback",
        "fallback_reason": "missing" if not ts_str else "invalid",
    }, None


def main():
    parser = argparse.ArgumentParser(description="Check backup freshness")
    parser.add_argument("--max-age-hours", type=float, default=24, help="Max age in hours (default: 24)")
    parser.add_argument("--backups-dir", type=str, default=None, help="Backups directory (default: auto-detect)")
    parser.add_argument("--allow-missing-manifest", action="store_true", help="Exit 0 when no manifest found (warn only)")
    args = parser.parse_args()

    project_root = _find_project_root()
    backups_dir = Path(args.backups_dir) if args.backups_dir else project_root / "artifacts" / "backups"

    manifest_files = sorted(backups_dir.glob("backup_manifest_*.json"), key=lambda f: f.name)

    now = datetime.now(timezone.utc)

    if not manifest_files:
        result = {
            "ok": args.allow_missing_manifest,
            "latest_manifest": None,
            "age_hours": None,
            "max_age_hours": args.max_age_hours,
            "checked_manifest_count": 0,
            "skipped_manifest_count": 0,
            "timestamp_source": None,
            "warnings": ["No backup manifest found"],
        }
        print(json.dumps(result, indent=2))
        sys.exit(0 if args.allow_missing_manifest else 1)

    candidates = []
    skipped = []
    warnings = []

    for mf in manifest_files:
        candidate, skip_name = _load_manifest_candidate(mf)
        if candidate is None:
            skipped.append(skip_name)
            warnings.append(f"Skipped invalid manifest: {skip_name}")
        else:
            if candidate["timestamp_source"] == "mtime_fallback":
                reason = candidate.get("fallback_reason", "unknown")
                warnings.append(f"Manifest {candidate['name']} used mtime fallback (timestamp {reason})")
            candidates.append(candidate)

    if not candidates:
        result = {
            "ok": False,
            "latest_manifest": None,
            "age_hours": None,
            "max_age_hours": args.max_age_hours,
            "checked_manifest_count": 0,
            "skipped_manifest_count": len(skipped),
            "timestamp_source": None,
            "warnings": warnings,
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    latest = max(candidates, key=lambda c: c["timestamp_dt"])

    age_hours = (now - latest["timestamp_dt"]).total_seconds() / 3600

    if age_hours > args.max_age_hours:
        warnings.append(f"Backup is {age_hours:.1f}h old, exceeds max {args.max_age_hours}h")

    ok = age_hours <= args.max_age_hours

    result = {
        "ok": ok,
        "latest_manifest": latest["name"],
        "age_hours": round(age_hours, 1),
        "max_age_hours": args.max_age_hours,
        "checked_manifest_count": len(candidates),
        "skipped_manifest_count": len(skipped),
        "timestamp_source": latest["timestamp_source"],
        "warnings": warnings,
    }

    print(json.dumps(result, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
