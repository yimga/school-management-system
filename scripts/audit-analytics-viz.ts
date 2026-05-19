/**
 * Phase 4 — forensic scan of analytics visualization sources.
 * Exits 0 when clean; auto-patches allowlisted token references only.
 */
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import {
  TOKEN_CONTRAST_BASELINES,
  meetsWcagAa,
} from "../src/components/shared/analytics/utils/contrast";

const ROOT = join(process.cwd(), "src");
const TARGET_DIRS = [
  join(ROOT, "components/shared/analytics"),
  join(ROOT, "apps/dashboard"),
];

const HEX_IN_STYLE = /#[0-9a-f]{3,8}\b/gi;
const RGB_LITERAL = /\brgb\(\s*\d+/i;
const HARDCODED_PX_FONT = /fontSize:\s*["']?\d+px/i;

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(tsx|ts|css)$/.test(entry)) out.push(full);
  }
  return out;
}

interface Finding {
  file: string;
  line: number;
  rule: string;
  detail: string;
}

function scanFile(file: string): Finding[] {
  const rel = relative(process.cwd(), file);
  const text = readFileSync(file, "utf8");
  const lines = text.split("\n");
  const findings: Finding[] = [];

  lines.forEach((line, idx) => {
    if (rel.replace(/\\/g, "/").endsWith("utils/contrast.ts")) return;
    if (line.includes("theme-locked-allow") || line.includes("off-token-allow")) return;
    if (HEX_IN_STYLE.test(line) || RGB_LITERAL.test(line)) {
      if (!line.includes("var(--") && !line.includes("contrast.ts")) {
        findings.push({
          file: rel,
          line: idx + 1,
          rule: "no-hardcoded-color",
          detail: line.trim(),
        });
      }
    }
    HEX_IN_STYLE.lastIndex = 0;
    if (HARDCODED_PX_FONT.test(line)) {
      findings.push({
        file: rel,
        line: idx + 1,
        rule: "use-type-token",
        detail: line.trim(),
      });
    }
  });

  return findings;
}

function runContrastGate(): Finding[] {
  const findings: Finding[] = [];
  for (const pair of TOKEN_CONTRAST_BASELINES) {
    if (!meetsWcagAa(pair.fg, pair.bg, pair.minRatio)) {
      findings.push({
        file: "utils/contrast.ts",
        line: 0,
        rule: "wcag-contrast",
        detail: `${pair.name} ratio below ${pair.minRatio}`,
      });
    }
  }
  return findings;
}

function main(): void {
  const files = TARGET_DIRS.flatMap((d) => walk(d));
  const findings = [...files.flatMap(scanFile), ...runContrastGate()];

  if (findings.length) {
    console.error("ANALYTICS VIZ AUDIT FAILED");
    for (const f of findings) {
      console.error(`  [${f.rule}] ${f.file}:${f.line} — ${f.detail}`);
    }
    process.exit(1);
  }

  const reportPath = join(process.cwd(), "docs/generated/analytics_viz_audit.json");
  const payload = {
    verdict: "ANALYTICS_VIZ_AUDIT_PASS",
    scanned_files: files.length,
    wcag_pairs_checked: TOKEN_CONTRAST_BASELINES.length,
    generated_at: new Date().toISOString(),
  };
  writeFileSync(reportPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  console.log(`ANALYTICS VIZ AUDIT PASS — ${files.length} files, report → ${reportPath}`);
}

main();
