import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const MOJIBAKE_CODE_POINTS = [
  0x9427, 0x95AD, 0x7480, 0x9983, 0x922B, 0x9241, 0x6DA4,
  0x93C4, 0x5909, 0x7075, 0x4F63, 0x8133, 0x95B2, 0x9422,
  0x93C8, 0x951B, 0xFFFD,
];

const MOJIBAKE_CHARS = MOJIBAKE_CODE_POINTS.map((cp) =>
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
  "src/lib/api.ts",
  "src/app/login/page.tsx",
  "src/app/register/page.tsx",
  "src/app/jobs/page.tsx",
  "src/components/UserSwitcher.tsx",
  "tests/e2e/auth.spec.ts",
  "tests/e2e/jobs.spec.ts",
  "tests/e2e/no-mojibake.spec.ts",
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
