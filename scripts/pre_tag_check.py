import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


_RESOLVED_GIT = None


def resolve_git():
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
        path_env = os.environ.get("PATH", "")
        for entry in path_env.split(os.pathsep):
            entry_lower = entry.lower().replace("\\", "/")
            if entry_lower.endswith("git/cmd") or entry_lower.endswith("git/cmd/"):
                candidate = os.path.join(entry, "git.exe")
                if os.path.isfile(candidate):
                    _RESOLVED_GIT = candidate
                    return candidate
    _RESOLVED_GIT = "git"
    return "git"


_FORBIDDEN_IN_OUTPUT = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"tp-[a-zA-Z0-9]{20,}"),
    re.compile(r"API_KEY=\S+"),
    re.compile(r"SECRET=\S+"),
    re.compile(r"PASSWORD=\S+"),
    re.compile(r"Authorization[=:]\S+"),
    re.compile(r"DATABASE_URL=\S+"),
]


def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "docker-compose.yml").exists() or (current / ".env.example").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path(__file__).resolve().parent


def _run_safe(cmd, timeout=30, cwd=None):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
        )
        return {"exit_code": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"exit_code": -1, "stdout": "", "stderr": "command not found"}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def _sanitize(text: str) -> str:
    for pat in _FORBIDDEN_IN_OUTPUT:
        text = pat.sub("<REDACTED>", text)
    return text


def _make_path_relative(text: str, project_root: Path) -> str:
    root_str = str(project_root)
    if root_str.endswith("\\") or root_str.endswith("/"):
        root_str = root_str[:-1]
    text = text.replace(root_str, "<project_root>")
    return text


def _check_release_notes(project_root: Path):
    rn = project_root / "docs" / "RELEASE_NOTES_v1.0.1-rc.1.md"
    if not rn.exists():
        return {"name": "release_notes_exist", "ok": False, "detail": "RELEASE_NOTES_v1.0.1-rc.1.md not found"}
    content = rn.read_text(encoding="utf-8")
    if "ALL CHECKS PASSED" in content:
        return {"name": "release_notes_no_false_claims", "ok": False, "detail": "Release notes contains ALL CHECKS PASSED without full gate execution"}
    return {"name": "release_notes_valid", "ok": True, "detail": "Release notes exists and no false claims"}


def _check_collect_evidence(project_root: Path):
    script = project_root / "scripts" / "collect_rc_evidence.py"
    if not script.exists():
        return {"name": "collect_evidence_exists", "ok": False, "detail": "collect_rc_evidence.py not found"}
    return {"name": "collect_evidence_exists", "ok": True, "detail": "collect_rc_evidence.py exists"}


def _check_artifacts_rc_gitignored(project_root: Path):
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        return {"name": "artifacts_rc_gitignored", "ok": False, "detail": ".gitignore not found"}
    content = gitignore.read_text(encoding="utf-8")
    if "artifacts/rc/" not in content:
        return {"name": "artifacts_rc_gitignored", "ok": False, "detail": "artifacts/rc/ not in .gitignore"}
    return {"name": "artifacts_rc_gitignored", "ok": True, "detail": "artifacts/rc/ is gitignored"}


def _check_env_not_tracked(project_root: Path):
    git_exe = resolve_git()
    result = _run_safe([git_exe, "ls-files", ".env"], timeout=10, cwd=str(project_root))
    if result["exit_code"] == -1 and "command not found" in result["stderr"]:
        return {"name": "env_not_tracked", "ok": False, "detail": "git unavailable, cannot verify .env tracking (manual check required)"}
    if result["exit_code"] != 0:
        return {"name": "env_not_tracked", "ok": False, "detail": "git command failed, cannot verify .env tracking (manual check required)"}
    if result["stdout"].strip():
        return {"name": "env_not_tracked", "ok": False, "detail": ".env is tracked by git"}
    return {"name": "env_not_tracked", "ok": True, "detail": ".env is not tracked by git"}


def _check_docs_secrets(project_root: Path):
    script = project_root / "scripts" / "check_docs_secrets.py"
    if not script.exists():
        return {"name": "docs_secrets_scan", "ok": False, "detail": "check_docs_secrets.py not found"}
    result = _run_safe([sys.executable, str(script)], timeout=60, cwd=str(project_root))
    if result["exit_code"] == 0:
        return {"name": "docs_secrets_scan", "ok": True, "detail": "passed"}
    return {"name": "docs_secrets_scan", "ok": False, "detail": f"failed (exit code {result['exit_code']})"}


def _check_mojibake(project_root: Path):
    script = project_root / "scripts" / "check_frontend_mojibake.py"
    if not script.exists():
        return {"name": "mojibake_scan", "ok": False, "detail": "check_frontend_mojibake.py not found"}
    result = _run_safe([sys.executable, str(script)], timeout=60, cwd=str(project_root))
    if result["exit_code"] == 0:
        return {"name": "mojibake_scan", "ok": True, "detail": "passed"}
    return {"name": "mojibake_scan", "ok": False, "detail": f"failed (exit code {result['exit_code']})"}


def _check_backup_freshness_workflow(project_root: Path):
    bf_yml = project_root / ".github" / "workflows" / "backup-freshness.yml"
    if not bf_yml.exists():
        return {"name": "backup_freshness_workflow", "ok": False, "detail": "backup-freshness.yml not found"}
    content = bf_yml.read_text(encoding="utf-8")
    if "BACKUP_FRESHNESS_ENABLED" not in content:
        return {"name": "backup_freshness_enable_gate", "ok": False, "detail": "BACKUP_FRESHNESS_ENABLED gate not found"}
    return {"name": "backup_freshness_workflow", "ok": True, "detail": "backup-freshness.yml exists with enable gate"}


def _check_ci_safety(project_root: Path):
    ci_yml = project_root / ".github" / "workflows" / "ci.yml"
    if not ci_yml.exists():
        return {"name": "ci_safety", "ok": False, "detail": "ci.yml not found"}
    content = ci_yml.read_text(encoding="utf-8")
    violations = []
    if "ConfirmRestore" in content:
        violations.append("ConfirmRestore found")
    if "eval_real_model" in content:
        violations.append("eval_real_model found")
    if "artifacts/backups" in content and "upload" in content.lower():
        violations.append("artifacts/backups upload found")
    if violations:
        return {"name": "ci_safety", "ok": False, "detail": "; ".join(violations)}
    return {"name": "ci_safety", "ok": True, "detail": "ci.yml has no dangerous commands"}


def _check_version_consistency(project_root: Path):
    config_py = project_root / "apps" / "api" / "app" / "config.py"
    env_example = project_root / ".env.example"
    api_contract = project_root / "docs" / "API_CONTRACT.md"

    versions = {}

    if config_py.exists():
        for line in config_py.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("APP_VERSION"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    versions["config.py"] = parts[1].strip().strip('"').strip("'")
                    break

    if env_example.exists():
        for line in env_example.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("APP_VERSION="):
                versions[".env.example"] = line.split("=", 1)[1].strip()
                break

    if api_contract.exists():
        content = api_contract.read_text(encoding="utf-8")
        import re as _re
        m = _re.search(r'"version":\s*"([^"]+)"', content)
        if m:
            versions["API_CONTRACT.md"] = m.group(1)

    if not versions:
        return {"name": "version_consistency", "ok": False, "detail": "no version found in any source"}

    unique_versions = set(versions.values())
    if len(unique_versions) == 1:
        return {"name": "version_consistency", "ok": True, "detail": f"all sources: {list(unique_versions)[0]}"}
    return {"name": "version_consistency", "ok": False, "detail": f"inconsistent versions: {versions}"}


def main():
    parser = argparse.ArgumentParser(description="Pre-tag check for v1.0.1-rc.1")
    parser.add_argument("--output-dir", type=str, default=None, help="Optional output directory for JSON result")
    args = parser.parse_args()

    project_root = _find_project_root()

    checks = [
        _check_release_notes(project_root),
        _check_collect_evidence(project_root),
        _check_artifacts_rc_gitignored(project_root),
        _check_env_not_tracked(project_root),
        _check_docs_secrets(project_root),
        _check_mojibake(project_root),
        _check_backup_freshness_workflow(project_root),
        _check_ci_safety(project_root),
        _check_version_consistency(project_root),
    ]

    warnings = [c for c in checks if c.get("warning")]
    failures = [c for c in checks if not c["ok"]]
    ok = len(failures) == 0

    result = {
        "ok": ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "warnings": [w["detail"] for w in warnings],
    }

    result_json = json.dumps(result, indent=2, ensure_ascii=False)
    result_json = _sanitize(result_json)
    result_json = _make_path_relative(result_json, project_root)

    print(result_json)

    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = project_root / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        out_path = output_dir / f"pre_tag_check_{ts}.json"
        out_path.write_text(result_json, encoding="utf-8")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
