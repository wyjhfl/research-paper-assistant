from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
API_BASE = "http://localhost:8091"
_RESOLVED_GIT: str | None = None


def resolve_git() -> str:
    """Resolve git robustly on Windows hosts with non-ASCII PATH entries."""
    global _RESOLVED_GIT
    if _RESOLVED_GIT is not None:
        return _RESOLVED_GIT
    found = shutil.which("git")
    if found:
        _RESOLVED_GIT = found
        return found
    if sys.platform == "win32":
        try:
            import winreg

            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(hive, r"SOFTWARE\GitForWindows")
                    install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    winreg.CloseKey(key)
                    candidate = os.path.join(install_path, "cmd", "git.exe")
                    if os.path.isfile(candidate):
                        _RESOLVED_GIT = candidate
                        return candidate
                except (FileNotFoundError, OSError):
                    pass
        except ImportError:
            pass
        for common in [
            os.path.join(os.environ.get("ProgramFiles", ""), "Git", "cmd", "git.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Git", "cmd", "git.exe"),
        ]:
            if common and os.path.isfile(common):
                _RESOLVED_GIT = common
                return common
        for entry in os.environ.get("PATH", "").split(os.pathsep):
            entry_lower = entry.lower().replace("\\", "/")
            if entry_lower.endswith("git/cmd") or entry_lower.endswith("git/cmd/"):
                candidate = os.path.join(entry, "git.exe")
                if os.path.isfile(candidate):
                    _RESOLVED_GIT = candidate
                    return candidate
    _RESOLVED_GIT = "git"
    return "git"


@dataclass
class Check:
    name: str
    ok: bool
    message: str


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _http_json(api_base: str, path: str, timeout: int = 10) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{api_base}{path}", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return True, json.dumps(data, ensure_ascii=False, sort_keys=True)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, type(exc).__name__


def check_git_safety() -> list[Check]:
    checks: list[Check] = []
    tracked = _run([
        resolve_git(),
        "ls-files",
        ".env",
        "artifacts/rc",
        "artifacts/evals",
        "artifacts/manual_papers",
        ".docker-temp",
    ])
    if tracked.returncode != 0:
        checks.append(Check("git ls-files sensitive paths", False, "git command failed"))
    else:
        leaked = [line for line in tracked.stdout.splitlines() if line.strip()]
        checks.append(
            Check(
                "git sensitive paths not tracked",
                not leaked,
                "none tracked" if not leaked else ", ".join(leaked),
            )
        )

    status = _run([resolve_git(), "status", "--short"], timeout=30)
    checks.append(
        Check(
            "git working tree",
            status.returncode == 0 and not status.stdout.strip(),
            "clean" if status.returncode == 0 and not status.stdout.strip() else "has changes",
        )
    )
    return checks


def check_docker() -> list[Check]:
    checks: list[Check] = []
    version = _run(["docker", "--version"], timeout=20)
    checks.append(
        Check(
            "docker available",
            version.returncode == 0,
            version.stdout.strip() if version.returncode == 0 else "docker command failed",
        )
    )
    if version.returncode != 0:
        return checks

    ps = _run(["docker", "compose", "ps", "--format", "json"], timeout=30)
    required = {"backend", "frontend", "postgres"}
    seen: dict[str, dict] = {}
    if ps.returncode == 0:
        for line in ps.stdout.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            service = item.get("Service")
            if service:
                seen[service] = item
    missing = sorted(required - set(seen))
    unhealthy = [
        name for name, item in seen.items()
        if item.get("State") != "running" or item.get("Health") not in ("", "healthy")
    ]
    ps_ok = ps.returncode == 0 and not missing and not unhealthy
    message = "backend/frontend/postgres running" if ps_ok else f"missing={missing}; unhealthy={unhealthy}"
    checks.append(Check("docker compose services running", ps_ok, message))
    return checks


def _http_status(url: str, timeout: int = 10) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 400, f"status={resp.status}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, type(exc).__name__


def _readiness_message(message: str) -> str:
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return message
    if data.get("ready") is True:
        return message

    current = data.get("alembic_current")
    head = data.get("alembic_head")
    if not current and not head:
        return message

    current_text = str(current) if current else "<unknown>"
    head_text = str(head) if head else "<unknown>"
    hint = (
        "readiness recovery hint: "
        f"alembic_current={current_text}; alembic_head={head_text}; "
        "see docs/LOCAL_DOCKER_RUNBOOK.md; "
        "first run read-only `docker compose exec -T backend python -m alembic current`; "
        "if the schema already exists and only version tracking is stale, manually run "
        f"non-destructive `docker compose exec -T backend python -m alembic stamp {head_text}`."
    )
    return f"{message}; {hint}"


def check_http(api_base: str, frontend_base: str) -> list[Check]:
    checks: list[Check] = []
    ok, msg = _http_json(api_base, "/health")
    checks.append(Check("GET /health", ok and '"status": "ok"' in msg, msg))
    ok, msg = _http_json(api_base, "/health/ready")
    ready_ok = ok and '"ready": true' in msg
    checks.append(Check("GET /health/ready", ready_ok, msg if ready_ok else _readiness_message(msg)))
    ok, msg = _http_status(frontend_base)
    checks.append(Check("GET frontend", ok, msg))
    return checks


def check_scripts(run_model_smoke: bool = False) -> list[Check]:
    checks: list[Check] = []
    smoke = _run(["docker", "compose", "exec", "-T", "backend", "python", "scripts/smoke_check.py"], timeout=120)
    checks.append(
        Check(
            "backend smoke_check.py",
            smoke.returncode == 0 and "RESULT: ALL CHECKS PASSED" in smoke.stdout,
            "passed" if smoke.returncode == 0 else "failed",
        )
    )
    if run_model_smoke:
        model = _run(["docker", "compose", "exec", "-T", "backend", "python", "scripts/model_smoke_check.py"], timeout=180)
        model_ok = model.returncode == 0 and "RESULT: ALL CHECKS PASSED" in model.stdout
        checks.append(Check("backend model_smoke_check.py", model_ok, "passed" if model_ok else "failed"))
    else:
        checks.append(Check("backend model_smoke_check.py", True, "skipped by default; pass --run-model-smoke to test real model connectivity"))
    return checks


def check_scanners() -> list[Check]:
    checks: list[Check] = []
    secret = _run([sys.executable, "scripts/check_docs_secrets.py"], timeout=60)
    checks.append(Check("check_docs_secrets.py", secret.returncode == 0, "passed" if secret.returncode == 0 else "failed"))
    mojibake = _run([sys.executable, "scripts/check_frontend_mojibake.py"], timeout=60)
    checks.append(Check("check_frontend_mojibake.py", mojibake.returncode == 0, "passed" if mojibake.returncode == 0 else "failed"))
    return checks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only personal local Docker health check.")
    parser.add_argument("--api-base", default=API_BASE, help="Backend API base URL, default http://localhost:8091")
    parser.add_argument("--frontend-base", default="http://localhost:3000", help="Frontend URL, default http://localhost:3000")
    parser.add_argument(
        "--skip-model-smoke",
        action="store_true",
        help="Deprecated no-op: model_smoke_check.py is skipped by default.",
    )
    parser.add_argument(
        "--run-model-smoke",
        action="store_true",
        help="Run model_smoke_check.py. This may call the configured real LLM provider.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checks: list[Check] = []
    checks.extend(check_git_safety())
    checks.extend(check_docker())
    if any(c.name == "docker available" and not c.ok for c in checks):
        print(json.dumps({"ok": False, "checks": [asdict(c) for c in checks]}, ensure_ascii=False, indent=2))
        return 1
    checks.extend(check_http(args.api_base.rstrip("/"), args.frontend_base.rstrip("/")))
    checks.extend(check_scripts(run_model_smoke=args.run_model_smoke))
    checks.extend(check_scanners())

    ok = all(c.ok for c in checks)
    print(json.dumps({"ok": ok, "checks": [asdict(c) for c in checks]}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
