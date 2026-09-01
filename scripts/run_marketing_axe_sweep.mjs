#!/usr/bin/env node
/**
 * Marketing axe sweep — enumerate + ratchet.
 *
 * Why this exists
 * ---------------
 * `tests/e2e/marketing-visual-truth.spec.js` runs axe with `expect.soft(
 * results.violations).toEqual([])`. That tells you a page failed; it does not
 * tell you WHICH colour pair failed, how many times, or whether the number
 * moved. This runner answers those questions and turns the stable part of the
 * answer into an enforceable ratchet.
 *
 * What is stable and what is not
 * ------------------------------
 * The raw violation TOTAL is not reproducible on this surface: the marketing
 * pages reveal content with IntersectionObserver (`[data-mkt-reveal]` →
 * `.is-revealed`), so two runs of the same tree sample different DOM and
 * returned 476 and 293 nodes. Ratcheting that number produces a gate that goes
 * red on its own and that people learn to ignore.
 *
 * Two things ARE stable and both are ratcheted here:
 *   * the set of PAGES that carry a serious/critical violation, and
 *   * the set of (rule, foreground, background) COLOUR PAIRS that fail
 *     contrast.
 * A colour pair is a property of the stylesheet, not of when axe sampled.
 *
 * The run additionally pins `reducedMotion: 'reduce'`, under which
 * static/marketing/js/marketing-motion.js reveals every `[data-mkt-reveal]`
 * synchronously (see its `reduce` branch). That removes the observer race
 * entirely, so this runner sees the whole page every time.
 *
 * Usage
 * -----
 *     node scripts/run_marketing_axe_sweep.mjs                # assert vs baseline
 *     node scripts/run_marketing_axe_sweep.mjs --write-baseline
 *     node scripts/run_marketing_axe_sweep.mjs --report       # enumerate only, exit 0
 *
 * Env: MARKETING_BASE_URL (default http://runmycampus.com:8010)
 *      AXE_SWEEP_OUT      (default artifacts/a11y/marketing-axe-sweep.json)
 */
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASE_URL = (
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  "http://runmycampus.com:8010"
).replace(/\/$/, "");
const OUT_PATH = path.resolve(
  ROOT,
  process.env.AXE_SWEEP_OUT || "artifacts/a11y/marketing-axe-sweep.json",
);
const BASELINE_PATH = path.resolve(ROOT, "var/a11y-marketing-axe-baseline.json");

// The UNION of the two page lists that already exist in the suite:
// tests/e2e/marketing-visual-truth.spec.js (home, hubs, v3 pages) and
// tests/e2e/marketing-accessibility.spec.js (platform + solutions pages).
// Scanning only one of them is how /platform/analytics/ and
// /platform/security/ kept a serious color-contrast failure while a sweep of
// the other list reported the surface clean.
const PAGES = [
  "/",
  "/pricing/",
  "/why-switch/",
  "/contact/",
  "/demo/",
  "/company/",
  "/resources/",
  "/developers/",
  "/solutions/head/",
  "/run/",
  "/teach/",
  "/pay/",
  "/communicate/",
  "/grow/",
  "/platform/",
  "/platform/integrations/",
  "/platform/admissions/",
  "/platform/fees-payments/",
  "/platform/parent-portal/",
  "/platform/teacher-portal/",
  "/platform/analytics/",
  "/platform/security/",
  "/solutions/private-schools/",
  "/solutions/international-schools/",
  "/solutions/multi-campus/",
  "/solutions/faith-based-schools/",
  "/solutions/growing-school-networks/",
];

const VIEWPORTS = [
  { label: "mobile", width: 375, height: 812 },
  { label: "desktop", width: 1280, height: 720 },
];

const BLOCKING_IMPACTS = new Set(["serious", "critical"]);

function pairKey(rule, data) {
  const fg = String(data?.fgColor ?? "").toLowerCase();
  const bg = String(data?.bgColor ?? "").toLowerCase();
  return `${rule}|${fg}|${bg}`;
}

async function main() {
  const mode = process.argv.includes("--write-baseline")
    ? "write"
    : process.argv.includes("--report")
      ? "report"
      : "assert";

  // The marketing surface is host-scoped (config.urls is chosen by Host), so a
  // bare 127.0.0.1 origin resolves a DIFFERENT urlconf and the sweep would scan
  // the wrong pages — see the host-split urlconf trap. Map the marketing host
  // at the browser resolver instead of editing the machine's hosts file.
  const hostRules =
    process.env.PLAYWRIGHT_HOST_RULES ||
    `MAP ${new URL(BASE_URL).hostname} 127.0.0.1`;
  const browser = await chromium.launch({
    args: [`--host-resolver-rules=${hostRules}`],
  });
  const results = [];
  const pairs = new Map();

  try {
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        // Determinism: reveals every [data-mkt-reveal] synchronously.
        reducedMotion: "reduce",
      });
      const page = await context.newPage();
      for (const route of PAGES) {
        const url = `${BASE_URL}${route}`;
        const label = `${route}@${vp.label}`;
        let violations = [];
        let incomplete = [];
        let error = null;
        try {
          await page.goto(url, { waitUntil: "load", timeout: 60_000 });
          await page.waitForTimeout(400);
          const scan = await new AxeBuilder({ page }).analyze();
          violations = scan.violations;
          // axe returns color-contrast as INCOMPLETE, not a violation, when it
          // cannot resolve the backdrop (a background image or gradient behind
          // the text). Those are not proof of a pass — one of them hid a real
          // 1.04:1 headline on the full-bleed globe band, found only by
          // measuring the element directly. Count them separately so the
          // report never presents "0 violations" as "nothing left to check".
          incomplete = (scan.incomplete || []).filter((v) => v.id === 'color-contrast');
        } catch (err) {
          error = String(err && err.message ? err.message : err);
        }

        const blocking = violations.filter((v) => BLOCKING_IMPACTS.has(v.impact));
        for (const v of violations) {
          for (const node of v.nodes) {
            for (const check of [...node.any, ...node.all, ...node.none]) {
              if (!check.data || typeof check.data !== "object") continue;
              if (check.data.fgColor === undefined) continue;
              const key = pairKey(v.id, check.data);
              const entry = pairs.get(key) || {
                rule: v.id,
                impact: v.impact,
                fg: String(check.data.fgColor).toLowerCase(),
                bg: String(check.data.bgColor).toLowerCase(),
                worst_ratio: Number.POSITIVE_INFINITY,
                required: check.data.expectedContrastRatio || null,
                instances: 0,
                sample_targets: [],
                pages: new Set(),
              };
              entry.instances += 1;
              const ratio = Number(check.data.contrastRatio);
              if (Number.isFinite(ratio)) {
                entry.worst_ratio = Math.min(entry.worst_ratio, ratio);
              }
              entry.pages.add(label);
              if (entry.sample_targets.length < 4) {
                entry.sample_targets.push(String(node.target));
              }
              pairs.set(key, entry);
            }
          }
        }

        results.push({
          page: label,
          route,
          viewport: vp.label,
          error,
          blocking_rules: [...new Set(blocking.map((v) => v.id))].sort(),
          blocking_nodes: blocking.reduce((n, v) => n + v.nodes.length, 0),
          all_rules: [...new Set(violations.map((v) => `${v.id}:${v.impact}`))].sort(),
          contrast_incomplete_nodes: incomplete.reduce((n, v) => n + v.nodes.length, 0),
        });
        process.stdout.write(
          `${label.padEnd(38)} blocking-rules=${
            results[results.length - 1].blocking_rules.join(",") || "none"
          }${error ? ` ERROR=${error}` : ""}\n`,
        );
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }

  const failingPages = results
    .filter((r) => r.blocking_rules.length > 0 || r.error)
    .map((r) => r.page)
    .sort();
  const pairList = [...pairs.values()]
    .map((p) => ({
      rule: p.rule,
      impact: p.impact,
      fg: p.fg,
      bg: p.bg,
      required: p.required,
      worst_ratio: Number.isFinite(p.worst_ratio)
        ? Math.round(p.worst_ratio * 100) / 100
        : null,
      instances: p.instances,
      pages: [...p.pages].sort(),
      sample_targets: p.sample_targets,
    }))
    .sort((a, b) => b.instances - a.instances);

  const summary = {
    base_url: BASE_URL,
    generated_at: new Date().toISOString(),
    pages_scanned: results.length,
    failing_page_count: failingPages.length,
    failing_pages: failingPages,
    contrast_incomplete_nodes: results.reduce(
      (n, r) => n + (r.contrast_incomplete_nodes || 0),
      0,
    ),
    // Colour pairs are keyed by rule+fg+bg — a stylesheet property, not a
    // sampling artefact. The instance COUNT is informational only and is
    // never asserted on (see module docstring).
    contrast_pairs: pairList,
    per_page: results,
  };

  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  fs.writeFileSync(OUT_PATH, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
  console.log(`\nwrote ${path.relative(ROOT, OUT_PATH)}`);
  console.log(`pages scanned      : ${summary.pages_scanned}`);
  console.log(`failing pages      : ${summary.failing_page_count}`);
  console.log(`failing colour pairs: ${pairList.length}`);
  const incompleteTotal = results.reduce((n, r) => n + (r.contrast_incomplete_nodes || 0), 0);
  console.log(
    `contrast nodes axe could NOT decide (background image/gradient): ${incompleteTotal}` +
      ` — not a pass; measure those directly (tests/e2e/marketing-contrast-tokens.spec.js)`,
  );
  for (const p of pairList) {
    console.log(
      `  ${p.rule} ${p.fg} on ${p.bg} — ${p.worst_ratio}:1 (need ${p.required}) ×${p.instances} on ${p.pages.length} page-views`,
    );
  }

  if (mode === "report") return 0;

  const ratchet = {
    max_failing_pages: summary.failing_page_count,
    allowed_contrast_pairs: pairList.map((p) => `${p.rule}|${p.fg}|${p.bg}`).sort(),
  };

  if (mode === "write") {
    fs.mkdirSync(path.dirname(BASELINE_PATH), { recursive: true });
    fs.writeFileSync(BASELINE_PATH, `${JSON.stringify(ratchet, null, 2)}\n`, "utf8");
    console.log(`\nwrote baseline ${path.relative(ROOT, BASELINE_PATH)}`);
    return 0;
  }

  if (!fs.existsSync(BASELINE_PATH)) {
    console.error(`\nMISSING BASELINE: ${BASELINE_PATH}`);
    return 1;
  }
  const base = JSON.parse(fs.readFileSync(BASELINE_PATH, "utf8"));
  const allowed = new Set(base.allowed_contrast_pairs || []);
  const newPairs = ratchet.allowed_contrast_pairs.filter((k) => !allowed.has(k));
  let rc = 0;
  if (summary.failing_page_count > (base.max_failing_pages ?? 0)) {
    console.error(
      `\nREGRESSION: failing pages ${summary.failing_page_count} > baseline ${base.max_failing_pages}`,
    );
    console.error(`  ${failingPages.join("\n  ")}`);
    rc = 1;
  }
  if (newPairs.length) {
    console.error(`\nREGRESSION: ${newPairs.length} colour pair(s) not in baseline:`);
    for (const k of newPairs) console.error(`  ${k}`);
    rc = 1;
  }
  if (rc === 0) {
    console.log("\nOK — no new failing pages and no new failing colour pairs.");
  }
  return rc;
}

main().then(
  (rc) => process.exit(rc),
  (err) => {
    console.error(err);
    process.exit(2);
  },
);
