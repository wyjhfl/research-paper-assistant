from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.config import settings, is_production, parse_cors_allowed_origins
from app.database import engine, check_db_connection


@dataclass
class CheckResult:
    name: str
    status: str
    message: str = ""


def _check_storage_path() -> CheckResult:
    storage = settings.STORAGE_PATH
    p = Path(storage)
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            return CheckResult("Storage path", "FAIL", "cannot create")
    if not os.access(str(p), os.W_OK):
        return CheckResult("Storage writable", "FAIL", "not writable")
    return CheckResult("Storage writable", "PASS", "")


def _check_eval_report() -> CheckResult:
    env_dir = os.environ.get("EVAL_REPORT_DIR", "").strip()
    if env_dir:
        report_path = Path(env_dir) / "real_model_eval_latest.json"
    else:
        report_path = Path.cwd() / "artifacts" / "evals" / "real_model_eval_latest.json"
    if report_path.exists():
        return CheckResult("Eval report", "PASS", "latest report found")
    return CheckResult("Eval report", "WARN", "missing")


def _check_cors() -> CheckResult:
    origins = parse_cors_allowed_origins(settings.CORS_ALLOWED_ORIGINS)
    if "*" in origins:
        if is_production():
            return CheckResult("CORS", "FAIL", "wildcard not allowed in production")
        return CheckResult("CORS", "WARN", "wildcard")
    if not origins:
        if is_production():
            return CheckResult("CORS", "FAIL", "no origins configured")
        return CheckResult("CORS", "WARN", "no origins configured")
    return CheckResult("CORS", "PASS", "configured")


def _check_real_model_required() -> CheckResult:
    if not settings.REAL_MODEL_REQUIRED:
        return CheckResult("Real model", "PASS", "not required")
    fails = []
    if settings.LLM_PROVIDER == "local":
        fails.append("LLM_PROVIDER is local")
    if settings.EMBEDDING_PROVIDER == "local":
        fails.append("EMBEDDING_PROVIDER is local")
    if fails:
        return CheckResult("Real model", "FAIL", "; ".join(fails))
    return CheckResult("Real model", "PASS", "configured")


def _parse_alembic_revision(output: str) -> str | None:
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        token = parts[0]
        if len(token) >= 8 and all(c in "0123456789abcdef" for c in token.lower()):
            return token.lower()
        if len(token) >= 3 and all(c.isalnum() or c == "_" for c in token) and not token.startswith("("):
            return token
    return None


def _check_alembic() -> CheckResult:
    alembic_dir = Path(__file__).resolve().parent.parent / "alembic"
    if not alembic_dir.exists():
        if is_production():
            return CheckResult("Alembic", "FAIL", "not initialized")
        return CheckResult("Alembic", "WARN", "not initialized")

    try:
        current_result = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        if current_result.returncode != 0:
            if is_production():
                return CheckResult("Alembic", "FAIL", "current command failed")
            return CheckResult("Alembic", "WARN", "current command failed")

        head_result = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        if head_result.returncode != 0:
            if is_production():
                return CheckResult("Alembic", "FAIL", "heads command failed")
            return CheckResult("Alembic", "WARN", "heads command failed")

        current_rev = _parse_alembic_revision(current_result.stdout)
        head_rev = _parse_alembic_revision(head_result.stdout)

        if current_rev is None:
            if is_production():
                return CheckResult("Alembic", "FAIL", "no current version")
            return CheckResult("Alembic", "WARN", "no current version")

        if head_rev is None:
            if is_production():
                return CheckResult("Alembic", "FAIL", "no head version")
            return CheckResult("Alembic", "WARN", "no head version")

        if current_rev == head_rev:
            return CheckResult("Alembic", "PASS", "at head")

        if is_production():
            return CheckResult("Alembic", "FAIL", "not at head")
        return CheckResult("Alembic", "WARN", "not at head")
    except Exception:
        if is_production():
            return CheckResult("Alembic", "FAIL", "check error")
        return CheckResult("Alembic", "WARN", "check error")


def _check_backup_dir() -> CheckResult:
    backup_base = Path.cwd() / "artifacts" / "backups"
    if not backup_base.exists():
        try:
            backup_base.mkdir(parents=True, exist_ok=True)
        except OSError:
            return CheckResult("Backup dir", "FAIL", "cannot create")
    if not os.access(str(backup_base), os.W_OK):
        return CheckResult("Backup dir", "FAIL", "not writable")
    return CheckResult("Backup dir", "PASS", "writable")


def _check_backup_manifest() -> CheckResult:
    backup_base = Path.cwd() / "artifacts" / "backups"
    if not backup_base.exists():
        return CheckResult("Backup manifest", "WARN", "no backups dir")
    manifests = sorted(backup_base.glob("backup_manifest_*.json"))
    if not manifests:
        return CheckResult("Backup manifest", "WARN", "no manifest found")
    try:
        raw = manifests[-1].read_bytes()
        if raw[:3] == b"\xef\xbb\xbf":
            raw = raw[3:]
        data = json.loads(raw.decode("utf-8"))
        if "app_version" not in data or "embedding_dimension" not in data:
            return CheckResult("Backup manifest", "WARN", "incomplete")
        if not data.get("db_backup_file"):
            return CheckResult("Backup manifest", "WARN", "missing db_backup_file")
        if not data.get("storage_backup_file"):
            return CheckResult("Backup manifest", "WARN", "missing storage_backup_file")
        return CheckResult("Backup manifest", "PASS", "found")
    except Exception:
        return CheckResult("Backup manifest", "WARN", "unreadable")


async def _check_embedding_dimension() -> CheckResult:
    if settings.EMBEDDING_PROVIDER == "local":
        return CheckResult("Embedding dimension", "PASS", "local provider, skip check")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT a.atttypmod FROM pg_attribute a "
                    "JOIN pg_class c ON a.attrelid = c.oid "
                    "JOIN pg_namespace n ON c.relnamespace = n.oid "
                    "WHERE c.relname='paper_chunks' AND a.attname='embedding' "
                    "AND n.nspname='public'"
                )
            )
            row = result.fetchone()
            if row is not None:
                db_dim = row[0]
                if db_dim > 0 and settings.EMBEDDING_DIMENSION != db_dim:
                    return CheckResult(
                        "Embedding dimension",
                        "WARN",
                        f"configured={settings.EMBEDDING_DIMENSION} db={db_dim}",
                    )
    except Exception:
        pass
    return CheckResult("Embedding dimension", "PASS", "")


def _check_auth_config() -> CheckResult:
    if not settings.AUTH_ENABLED:
        if is_production():
            return CheckResult("Auth config", "FAIL", "AUTH_ENABLED must be true in production")
        return CheckResult("Auth config", "WARN", "AUTH_ENABLED=false (dev mode)")

    if settings.ALLOW_DEV_USER_HEADER:
        if is_production():
            return CheckResult("Auth config", "FAIL", "ALLOW_DEV_USER_HEADER must be false in production")
        return CheckResult("Auth config", "WARN", "ALLOW_DEV_USER_HEADER=true (insecure for production)")

    if not settings.SESSION_COOKIE_SECURE:
        if is_production():
            return CheckResult("Auth cookie", "FAIL", "SESSION_COOKIE_SECURE must be true in production")
        return CheckResult("Auth cookie", "WARN", "SESSION_COOKIE_SECURE=false")

    if settings.SESSION_TTL_SECONDS <= 0:
        return CheckResult("Auth session TTL", "FAIL", "SESSION_TTL_SECONDS must be > 0")

    return CheckResult("Auth config", "PASS", "enabled, dev header disabled")


def _check_job_config() -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(CheckResult("Job worker", "PASS", f"JOB_WORKER_ENABLED={settings.JOB_WORKER_ENABLED}"))
    if settings.JOB_POLL_INTERVAL_SECONDS <= 0:
        results.append(CheckResult("Job poll interval", "FAIL", "JOB_POLL_INTERVAL_SECONDS must be > 0"))
    else:
        results.append(CheckResult("Job poll interval", "PASS", f"{settings.JOB_POLL_INTERVAL_SECONDS}s"))
    if settings.JOB_MAX_ATTEMPTS < 1:
        results.append(CheckResult("Job max attempts", "FAIL", "JOB_MAX_ATTEMPTS must be >= 1"))
    else:
        results.append(CheckResult("Job max attempts", "PASS", str(settings.JOB_MAX_ATTEMPTS)))
    if settings.JOB_STALE_RUNNING_SECONDS <= 0:
        results.append(CheckResult("Job stale running", "FAIL", "JOB_STALE_RUNNING_SECONDS must be > 0"))
    else:
        results.append(CheckResult("Job stale running", "PASS", f"{settings.JOB_STALE_RUNNING_SECONDS}s"))
    return results


def _check_maintenance_scripts() -> CheckResult:
    scripts_dir = Path(__file__).resolve().parent
    required = ["storage_audit.py", "cleanup_storage.py", "cleanup_jobs.py", "validate_backup_manifest.py"]
    missing = [s for s in required if not (scripts_dir / s).exists()]
    if missing:
        return CheckResult("Maintenance scripts", "WARN", f"missing: {', '.join(missing)}")
    return CheckResult("Maintenance scripts", "PASS", "all present")


def _check_validate_manifest_script() -> CheckResult:
    script_path = Path(__file__).resolve().parent / "validate_backup_manifest.py"
    if not script_path.exists():
        if is_production():
            return CheckResult("Validate manifest script", "FAIL", "validate_backup_manifest.py not found")
        return CheckResult("Validate manifest script", "WARN", "validate_backup_manifest.py not found")
    return CheckResult("Validate manifest script", "PASS", "present")


async def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []

    db_ok = await check_db_connection()
    results.append(CheckResult(
        "Database", "PASS" if db_ok else "FAIL",
        "" if db_ok else "connection failed",
    ))

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            )
            row = result.fetchone()
            if row is not None:
                results.append(CheckResult("pgvector", "PASS", f"v{row[0]}"))
            else:
                results.append(CheckResult("pgvector", "FAIL", "extension not found"))
    except Exception:
        results.append(CheckResult("pgvector", "FAIL", "check error"))

    required_tables = [
        "papers", "paper_chunks", "ideas", "idea_sources",
        "agent_runs", "job_runs", "model_call_events", "users", "user_sessions",
    ]
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
            )
            existing = {row[0] for row in result.fetchall()}
            missing = [t for t in required_tables if t not in existing]
            if missing:
                results.append(CheckResult("Core tables", "FAIL", f"missing: {', '.join(missing)}"))
            else:
                results.append(CheckResult("Core tables", "PASS", "all present"))
    except Exception:
        results.append(CheckResult("Core tables", "FAIL", "check error"))

    results.append(_check_storage_path())
    results.append(_check_eval_report())
    results.append(_check_cors())
    results.append(_check_real_model_required())
    results.append(_check_alembic())
    results.append(_check_backup_dir())
    results.append(_check_backup_manifest())
    results.append(_check_auth_config())
    results.extend(_check_job_config())
    results.append(_check_maintenance_scripts())
    results.append(_check_validate_manifest_script())
    results.append(CheckResult("ENV", "PASS", f"ENV={settings.ENV}"))

    if db_ok:
        results.append(await _check_embedding_dimension())

    return results


def print_results(results: list[CheckResult]) -> int:
    print("=" * 60)
    print("Research Paper Assistant - Production Check")
    print("=" * 60)
    print(f"Version: {settings.APP_VERSION}")
    print()

    has_fail = False
    has_warn = False

    for r in results:
        label = r.name
        if r.message:
            label = f"{r.name}: {r.message}"
        print(f"  {r.status}: {label}")
        if r.status == "FAIL":
            has_fail = True
        elif r.status == "WARN":
            has_warn = True

    print()
    print("=" * 60)
    if has_fail:
        print("RESULT: FAIL")
    elif has_warn:
        print("RESULT: PASS WITH WARNINGS")
    else:
        print("RESULT: ALL CHECKS PASSED")
    print("=" * 60)

    return 1 if has_fail else 0


async def main():
    results = await run_checks()
    exit_code = print_results(results)
    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
