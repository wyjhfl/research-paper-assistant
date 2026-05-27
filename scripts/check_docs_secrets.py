#!/usr/bin/env python3
"""Scan documentation files for suspected secrets / sensitive information.

Allowed placeholders (whitelist):
  - <YOUR_...>
  - <REPLACE_ME>
  - "configured"
  - "example"

Local dev database defaults (strict match only):
  - postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant
  - postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant_test

Exit 0 if clean, exit 1 if real secrets found.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCAN_PATHS: list[Path] = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "docs",
]

PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<YOUR_[A-Z_]+>"),
    re.compile(r"<REPLACE_ME>"),
]

SAFE_LITERAL_EXACT: list[str] = [
    "configured",
    "example",
]

LOCAL_DEV_DB_EXACT: list[str] = [
    "postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant_test",
]


@dataclass
class Rule:
    name: str
    pattern: re.Pattern[str]
    group: int = 1


RULES: list[Rule] = [
    Rule("tp-token", re.compile(r"tp-([A-Za-z0-9]{16,})")),
    Rule("sk-token", re.compile(r"sk-([A-Za-z0-9]{16,})")),
    Rule("authorization-bearer", re.compile(r"Authorization:\s*Bearer\s+(\S+)", re.IGNORECASE)),
    Rule("api-key-assign", re.compile(r"API_KEY\s*=\s*(\S+)", re.IGNORECASE)),
    Rule("password-assign", re.compile(r"PASSWORD\s*=\s*(\S+)", re.IGNORECASE)),
    Rule("database-url-assign", re.compile(r"DATABASE_URL\s*=\s*(\S+)", re.IGNORECASE)),
    Rule("postgresql-connection", re.compile(r"(postgresql\+asyncpg://\S+)", re.IGNORECASE)),
]


def _is_placeholder(value: str) -> bool:
    for pat in PLACEHOLDER_PATTERNS:
        if pat.fullmatch(value):
            return True
    for literal in SAFE_LITERAL_EXACT:
        if value == literal:
            return True
    return False


def _is_local_dev_db(value: str) -> bool:
    return value in LOCAL_DEV_DB_EXACT


def _redact(value: str, visible: int = 4) -> str:
    if len(value) <= visible:
        return "***"
    return value[:visible] + "..." + f"({len(value)} chars)"


def _safe_relative(filepath: Path) -> str:
    try:
        return str(filepath.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(filepath)


@dataclass
class Finding:
    file: str
    line: int
    rule_name: str
    redacted: str


def scan_file(filepath: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        lines = filepath.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return findings

    for lineno, line in enumerate(lines, start=1):
        for rule in RULES:
            for m in rule.pattern.finditer(line):
                value = m.group(rule.group)
                if _is_placeholder(value):
                    continue
                if rule.name == "postgresql-connection" and _is_local_dev_db(value):
                    continue
                if rule.name == "database-url-assign" and _is_local_dev_db(value):
                    continue
                findings.append(
                    Finding(
                        file=_safe_relative(filepath),
                        line=lineno,
                        rule_name=rule.name,
                        redacted=_redact(value),
                    )
                )
    return findings


def scan_all() -> list[Finding]:
    all_findings: list[Finding] = []
    for path in SCAN_PATHS:
        if path.is_file():
            all_findings.extend(scan_file(path))
        elif path.is_dir():
            for md in sorted(path.rglob("*.md")):
                all_findings.extend(scan_file(md))
    return all_findings


def main() -> None:
    findings = scan_all()
    if not findings:
        print("DOC SECRET CHECK PASSED")
        sys.exit(0)

    print("DOC SECRET CHECK FAILED — suspected secrets found:")
    for f in findings:
        print(f"  {f.file}:{f.line}  [{f.rule_name}]  value={f.redacted}")
    sys.exit(1)


if __name__ == "__main__":
    main()
