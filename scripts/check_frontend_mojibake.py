#!/usr/bin/env python3
"""Check frontend source files for mojibake code points and UTF-8 BOM."""

import sys
from pathlib import Path

MOJIBAKE_CODE_POINTS = [
    0x9427, 0x95AD, 0x7480, 0x9983, 0x922B, 0x9241, 0x6DA4,
    0x93C4, 0x5909, 0x7075, 0x4F63, 0x8133, 0x95B2, 0x9422,
    0x93C8, 0x951B, 0xFFFD,
]

DISCOURAGED_CODE_POINTS = [
    0x00B7,  # middle dot
    0x00D7,  # multiplication sign used as close icon
    0x2013,  # en dash
    0x2014,  # em dash
    0x2192,  # arrow
    0x1F4A1, 0x1F4AC, 0x1F4C4, 0x1F4CA, 0x1F4DA, 0x1F50D, 0x1F527, 0x1F916,
]

MOJIBAKE_SUBSTRINGS = [
    'icon="??"',
    'icon: "??"',
    ">??<",
    "馃",
    "鈫",
    "鉁",
    "锛",
    "銆",
    "Ў",
]

SCAN_FILES = [
    "apps/web/src/app/page.tsx",
    "apps/web/src/app/loading.tsx",
    "apps/web/src/app/not-found.tsx",
    "apps/web/src/app/ideas/page.tsx",
    "apps/web/src/app/ideas/[id]/page.tsx",
    "apps/web/src/app/papers/page.tsx",
    "apps/web/src/app/papers/[id]/page.tsx",
    "apps/web/src/app/mcp/page.tsx",
    "apps/web/src/lib/api.ts",
    "apps/web/src/app/login/page.tsx",
    "apps/web/src/app/register/page.tsx",
    "apps/web/src/app/jobs/page.tsx",
    "apps/web/src/components/EmptyState.tsx",
    "apps/web/src/components/EvidenceSourcesPanel.tsx",
    "apps/web/src/components/IdeaExtractor.tsx",
    "apps/web/src/components/MultiPaperQA.tsx",
    "apps/web/src/components/PaperDetailClient.tsx",
    "apps/web/src/components/PaperQA.tsx",
    "apps/web/src/components/PaperTable.tsx",
    "apps/web/src/components/UserSwitcher.tsx",
    "apps/web/src/components/UsageDashboard.tsx",
    "apps/web/tests/e2e/auth.spec.ts",
    "apps/web/tests/e2e/jobs.spec.ts",
]


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    errors = 0

    for rel_path in SCAN_FILES:
        file_path = repo_root / rel_path
        if not file_path.exists():
            print(f"MISSING: {rel_path}")
            errors += 1
            continue

        raw = file_path.read_bytes()

        if len(raw) >= 3 and raw[0] == 0xEF and raw[1] == 0xBB and raw[2] == 0xBF:
            print(f"BOM: {rel_path} has UTF-8 BOM")
            errors += 1

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            print(f"DECODE ERROR: {rel_path}: {exc}")
            errors += 1
            continue

        for cp in MOJIBAKE_CODE_POINTS:
            ch = chr(cp)
            if ch in content:
                print(f"MOJIBAKE: {rel_path} contains U+{cp:04X}")
                errors += 1
        for cp in DISCOURAGED_CODE_POINTS:
            ch = chr(cp)
            if ch in content:
                print(f"DISCOURAGED UNICODE: {rel_path} contains U+{cp:04X}")
                errors += 1
        for marker in MOJIBAKE_SUBSTRINGS:
            if marker in content:
                print(f"MOJIBAKE TEXT: {rel_path} contains {ascii(marker)}")
                errors += 1

    if errors == 0:
        print("FRONTEND MOJIBAKE CHECK PASSED")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
