from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SECRET_PATTERNS = [
    re.compile(r"tp-[A-Za-z0-9]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Authorization", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"postgresql\+?://\S+@\S+"),
    re.compile(r"DATABASE_URL", re.IGNORECASE),
]

REQUIRED_FIELDS = ["timestamp", "db_backup_file", "storage_backup_file"]


def _check_secrets(data: dict) -> list[str]:
    raw = json.dumps(data)
    findings: list[str] = []
    for pat in SECRET_PATTERNS:
        for m in pat.finditer(raw):
            matched = m.group(0)
            if matched in ("app_version", "embedding_dimension"):
                continue
            if "<YOUR_" in matched or "<REPLACE_ME" in matched:
                continue
            findings.append(matched)
    return findings


def validate_manifest(manifest_path: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    manifest_file = Path(manifest_path)

    if not manifest_file.exists():
        return {"ok": False, "errors": ["manifest not found"], "warnings": []}

    raw = manifest_file.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]

    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "errors": [f"JSON decode error: {exc}"], "warnings": []}

    if not isinstance(data, dict):
        return {"ok": False, "errors": ["manifest is not a JSON object"], "warnings": []}

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")
        elif not data[field]:
            errors.append(f"empty required field: {field}")

    manifest_dir = manifest_file.resolve().parent

    for file_field, sub_dir in [("db_backup_file", "db"), ("storage_backup_file", "storage")]:
        fname = data.get(file_field, "")
        if fname:
            fpath = manifest_dir / sub_dir / fname
            if not fpath.exists():
                errors.append(f"referenced file not found: {file_field}={fname}")

    eval_fname = data.get("eval_backup_file", "")
    if eval_fname:
        eval_path = manifest_dir / "evals" / eval_fname
        if not eval_path.exists():
            warnings.append(f"eval backup file not found: {eval_fname}")

    secret_findings = _check_secrets(data)
    if secret_findings:
        errors.append(f"manifest contains secret-like values: {secret_findings[:3]}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_backup_manifest.py <manifest_path>", file=sys.stderr)
        sys.exit(1)

    result = validate_manifest(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
