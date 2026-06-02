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


_FORBIDDEN_PATTERNS = [
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


def _sanitize(text: str) -> str:
    for pat in _FORBIDDEN_PATTERNS:
        text = pat.sub("<REDACTED>", text)
    return text


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


def _get_git_info(project_root: Path):
    info = {"available": False}
    git_exe = resolve_git()
    result = _run_safe([git_exe, "rev-parse", "--abbrev-ref", "HEAD"], timeout=10, cwd=str(project_root))
    if result["exit_code"] == 0:
        info["available"] = True
        info["branch"] = result["stdout"]
    else:
        info["branch"] = "unavailable"

    result = _run_safe([git_exe, "rev-parse", "HEAD"], timeout=10, cwd=str(project_root))
    if result["exit_code"] == 0:
        info["commit"] = result["stdout"]
    else:
        info["commit"] = "unavailable"

    result = _run_safe([git_exe, "status", "--porcelain"], timeout=10, cwd=str(project_root))
    if result["exit_code"] == 0:
        info["dirty"] = len(result["stdout"]) > 0
    else:
        info["dirty"] = "unavailable"

    return info


def _get_version_info(project_root: Path):
    version_info = {}
    config_py = project_root / "apps" / "api" / "app" / "config.py"
    if config_py.exists():
        for line in config_py.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("APP_VERSION"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    version_info["app_version"] = parts[1].strip().strip('"').strip("'")
                    break
    if not version_info.get("app_version"):
        env_example = project_root / ".env.example"
        if env_example.exists():
            for line in env_example.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("APP_VERSION="):
                    version_info["app_version"] = line.split("=", 1)[1].strip()
                    break
    if not version_info.get("app_version"):
        version_info["app_version"] = "unknown"
    return version_info


def _check_workflow_files(project_root: Path):
    workflows = {}
    ci_yml = project_root / ".github" / "workflows" / "ci.yml"
    bf_yml = project_root / ".github" / "workflows" / "backup-freshness.yml"
    workflows["ci_yml_exists"] = ci_yml.exists()
    workflows["backup_freshness_yml_exists"] = bf_yml.exists()
    if bf_yml.exists():
        content = bf_yml.read_text(encoding="utf-8")
        workflows["backup_freshness_has_enable_gate"] = "BACKUP_FRESHNESS_ENABLED" in content
    return workflows


def _run_scanner(project_root: Path, script_name: str):
    script = project_root / "scripts" / script_name
    if not script.exists():
        return {"status": "script_not_found", "exit_code": -1}
    result = _run_safe([sys.executable, str(script)], timeout=60, cwd=str(project_root))
    return {
        "status": "passed" if result["exit_code"] == 0 else "failed",
        "exit_code": result["exit_code"],
    }


def _make_path_relative(text: str, project_root: Path) -> str:
    root_str = str(project_root)
    if root_str.endswith("\\") or root_str.endswith("/"):
        root_str = root_str[:-1]
    text = text.replace(root_str, "<project_root>")
    return text


def collect_evidence(output_dir: Path, project_root: Path):
    now = datetime.now(timezone.utc)
    ts_compact = now.strftime("%Y%m%d_%H%M%SZ")

    evidence = {
        "timestamp": now.isoformat(),
        "version": _get_version_info(project_root),
        "git": _get_git_info(project_root),
        "workflows": _check_workflow_files(project_root),
        "scanners": {
            "docs_secrets": _run_scanner(project_root, "check_docs_secrets.py"),
            "frontend_mojibake": _run_scanner(project_root, "check_frontend_mojibake.py"),
        },
        "backup_freshness_note": "Schedule requires BACKUP_FRESHNESS_ENABLED=true repository variable. workflow_dispatch is not gated.",
        "constraints": {
            "no_env_content": True,
            "no_api_keys": True,
            "no_authorization": True,
            "no_database_url": True,
            "no_session_tokens": True,
            "no_backup_artifacts": True,
            "no_eval_artifacts": True,
            "no_absolute_paths": True,
        },
    }

    evidence_json = json.dumps(evidence, indent=2, ensure_ascii=False)
    evidence_json = _sanitize(evidence_json)
    evidence_json = _make_path_relative(evidence_json, project_root)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"rc_evidence_{ts_compact}.json"
    json_path.write_text(evidence_json, encoding="utf-8")

    md_lines = [
        f"# RC Evidence Pack",
        f"",
        f"- **Timestamp**: {now.isoformat()}",
        f"- **App Version**: {evidence['version'].get('app_version', 'unknown')}",
        f"- **Git Branch**: {evidence['git'].get('branch', 'unavailable')}",
        f"- **Git Commit**: {evidence['git'].get('commit', 'unavailable')}",
        f"- **Git Dirty**: {evidence['git'].get('dirty', 'unavailable')}",
        f"",
        f"## Workflow Files",
        f"",
        f"| Workflow | Exists |",
        f"|----------|--------|",
        f"| ci.yml | {'Yes' if evidence['workflows']['ci_yml_exists'] else 'No'} |",
        f"| backup-freshness.yml | {'Yes' if evidence['workflows']['backup_freshness_yml_exists'] else 'No'} |",
        f"",
        f"## Scanner Results",
        f"",
        f"| Scanner | Status | Exit Code |",
        f"|---------|--------|-----------|",
        f"| docs_secrets | {evidence['scanners']['docs_secrets']['status']} | {evidence['scanners']['docs_secrets']['exit_code']} |",
        f"| frontend_mojibake | {evidence['scanners']['frontend_mojibake']['status']} | {evidence['scanners']['frontend_mojibake']['exit_code']} |",
        f"",
        f"## Backup Freshness",
        f"",
        f"Schedule requires `BACKUP_FRESHNESS_ENABLED=true` repository variable. workflow_dispatch is not gated.",
        f"",
        f"## Constraints",
        f"",
        f"- No .env content",
        f"- No API keys",
        f"- No Authorization headers",
        f"- No DATABASE_URL real values",
        f"- No session tokens",
        f"- No backup artifacts content",
        f"- No eval artifacts content",
        f"- No absolute paths",
        f"",
        f"## JSON Evidence",
        f"",
        f"See `{json_path.name}`",
    ]
    md_content = "\n".join(md_lines)
    md_content = _sanitize(md_content)
    md_content = _make_path_relative(md_content, project_root)
    md_path = output_dir / f"rc_evidence_{ts_compact}.md"
    md_path.write_text(md_content, encoding="utf-8")

    return json_path, md_path


def main():
    parser = argparse.ArgumentParser(description="Collect RC evidence pack")
    parser.add_argument("--output-dir", type=str, default="artifacts/rc", help="Output directory (default: artifacts/rc)")
    args = parser.parse_args()

    project_root = _find_project_root()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    json_path, md_path = collect_evidence(output_dir, project_root)

    print(f"RC evidence collected:")
    print(f"  JSON: {json_path.name}")
    print(f"  MD:   {md_path.name}")

    evidence = json.loads(json_path.read_text(encoding="utf-8"))
    scanner_failed = False
    for name, result in evidence.get("scanners", {}).items():
        if result.get("status") == "failed":
            print(f"  WARNING: {name} scanner failed (exit code {result['exit_code']})")
            scanner_failed = True

    if scanner_failed:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
