import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const MOJIBAKE_CODE_POINTS = [
  0x9427, 0x95AD, 0x7480, 0x9983, 0x922B, 0x9241, 0x6DA4,
  0x93C4, 0x5909, 0x7075, 0x4F63, 0x8133, 0x95B2, 0x9422,
  0x93C8, 0x951B, 0xFFFD,
];

const DISCOURAGED_CODE_POINTS = [
  0x00B7, 0x00D7, 0x2013, 0x2014, 0x2192,
  0x1F4A1, 0x1F4AC, 0x1F4C4, 0x1F4CA, 0x1F4DA, 0x1F50D, 0x1F527, 0x1F916,
];

const MOJIBAKE_SUBSTRINGS = ['icon="??"', 'icon: "??"', ">??<", "馃", "鈫", "鉁", "锛", "銆", "Ў"];

const MOJIBAKE_CHARS = MOJIBAKE_CODE_POINTS.map((cp) =>
  String.fromCodePoint(cp)
);
const DISCOURAGED_CHARS = DISCOURAGED_CODE_POINTS.map((cp) =>
  String.fromCodePoint(cp)
);

function buildMojibakeRe(): RegExp {
  const parts = MOJIBAKE_CODE_POINTS.map((cp) => {
    if (cp === 0xFFFD) return "\\ufffd";
    return String.fromCodePoint(cp);
  });
  return new RegExp(parts.join("|"));
}

const MOJIBAKE_RE = buildMojibakeRe();

const SCAN_FILES = [
  "src/app/page.tsx",
  "src/app/loading.tsx",
  "src/app/not-found.tsx",
  "src/app/guide/page.tsx",
  "src/app/ideas/page.tsx",
  "src/app/ideas/[id]/page.tsx",
  "src/app/papers/page.tsx",
  "src/app/papers/[id]/page.tsx",
  "src/app/papers/review/page.tsx",
  "src/app/notes/page.tsx",
  "src/app/mcp/page.tsx",
  "src/app/layout.tsx",
  "src/lib/api.ts",
  "src/app/login/page.tsx",
  "src/app/register/page.tsx",
  "src/app/jobs/page.tsx",
  "src/components/EmptyState.tsx",
  "src/components/EvidenceSourcesPanel.tsx",
  "src/components/IdeaExtractor.tsx",
  "src/components/MultiPaperQA.tsx",
  "src/components/PaperDetailClient.tsx",
  "src/components/PaperQA.tsx",
  "src/components/ReviewMatrix.tsx",
  "src/components/NotesWorkbench.tsx",
  "src/components/LocalLandingStatus.tsx",
  "src/components/PaperTable.tsx",
  "src/components/UserSwitcher.tsx",
  "src/components/UsageDashboard.tsx",
  "tests/e2e/auth.spec.ts",
  "tests/e2e/jobs.spec.ts",
];

for (const relPath of SCAN_FILES) {
  test(`${relPath} no mojibake code points`, () => {
    const filePath = path.resolve(__dirname, "../../", relPath);
    const content = fs.readFileSync(filePath, "utf-8");
    for (let i = 0; i < MOJIBAKE_CHARS.length; i++) {
      const ch = MOJIBAKE_CHARS[i];
      if (content.includes(ch)) {
        const cp = MOJIBAKE_CODE_POINTS[i];
        throw new Error(
          `${relPath} contains mojibake code point U+${cp.toString(16).toUpperCase().padStart(4, "0")}`
        );
      }
    }
    expect(content).not.toMatch(MOJIBAKE_RE);
    for (let i = 0; i < DISCOURAGED_CHARS.length; i++) {
      const ch = DISCOURAGED_CHARS[i];
      if (content.includes(ch)) {
        const cp = DISCOURAGED_CODE_POINTS[i];
        throw new Error(
          `${relPath} contains discouraged Unicode U+${cp.toString(16).toUpperCase().padStart(4, "0")}`
        );
      }
    }
    for (const marker of MOJIBAKE_SUBSTRINGS) {
      expect(content, `${relPath} contains mojibake marker ${marker}`).not.toContain(marker);
    }
  });
}

test("all scan files are valid UTF-8 without BOM", () => {
  for (const relPath of SCAN_FILES) {
    const filePath = path.resolve(__dirname, "../../", relPath);
    const bytes = fs.readFileSync(filePath);
    const hasBom =
      bytes.length >= 3 &&
      bytes[0] === 0xef &&
      bytes[1] === 0xbb &&
      bytes[2] === 0xbf;
    expect(hasBom, `${relPath} has UTF-8 BOM`).toBe(false);

    const content = bytes.toString("utf-8");
    expect(content).not.toMatch(MOJIBAKE_RE);
  }
});
