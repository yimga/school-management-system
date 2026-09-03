/** @type {import('lighthouse').Config} */
const strictN10 = process.env.LHCI_STRICT_N10 === "1";
const perfLevel = strictN10 ? "error" : "warn";
const perfMin = strictN10 ? 0.82 : 0.75;
const lcpMax = strictN10 ? 3500 : 4000;

const primary = (process.env.LHCI_URL || "http://127.0.0.1:8000/").trim();
const extrasRaw = (process.env.LHCI_URLS_EXTRA || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

/**
 * Same-origin paths as docs/LHCI_STAGING_GITHUB_VARS.md recommended bundle.
 * Enable with LHCI_AUTO_EXTRAS=1 to avoid duplicating long LHCI_URLS_EXTRA in GitHub vars.
 */
function autoExtrasFromPrimary(p) {
  try {
    const u = new URL(p);
    const o = u.origin;
    const paths = [
      "/marketing/",
      "/platform/",
      "/education-operating-system/",
      "/portal/parent/",
      "/portal/teacher/bulk-capture/",
      "/verify/",
      "/support/",
    ];
    return paths.map((x) => o + x);
  } catch {
    return [];
  }
}

const autoOn = process.env.LHCI_AUTO_EXTRAS === "1";
const autoUrls = autoOn ? autoExtrasFromPrimary(primary) : [];
const seen = new Set();
const urls = [];
for (const u of [primary, ...extrasRaw, ...autoUrls]) {
  if (u && !seen.has(u)) {
    seen.add(u);
    urls.push(u);
  }
}

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 1,
      url: urls,
    },
    assert: {
      assertions: {
        // ACCESSIBILITY, at error level. This config is the one both
        // lighthouse-ci.yml and lighthouse-ci-local.yml load, and until
        // 2026-09-01 it asserted only performance and Core Web Vitals -- so
        // every Lighthouse run CI has ever done was silent about
        // accessibility, which is the one category Lighthouse is most reliable
        // about. (lighthouserc.js, a DIFFERENT file, has always carried this
        // assertion and is loaded by `npm run lighthouse` only.)
        //
        // Measured 2026-09-01 with Lighthouse 12.8.2 against a local
        // runserver, one run per URL, mobile emulation, forced light scheme:
        //   /marketing/                      100
        //   /platform/                       100
        //   /education-operating-system/      96 -> 100 after the
        //                                    .link-secondary fix in
        //                                    marketing-accessibility-hardening.css
        //   /verify/                         100
        //   /support/                        100
        //   /authentication/login/           100
        // 0.95 leaves a single-audit margin without being toothless: the two
        // authenticated LHCI_AUTO_EXTRAS paths redirect to the login page,
        // which itself measured 100.
        "categories:accessibility": ["error", { minScore: 0.95 }],
        "categories:performance": [perfLevel, { minScore: perfMin }],
        // 12-pillar audit P1 — Core Web Vitals "good" thresholds per web.dev.
        // LCP good = 2500ms; the existing 4000/3500 budget stays as the warn
        // threshold via lcpMax, and the strict tightening kicks in under
        // LHCI_STRICT_N10=1 (production gate).
        "largest-contentful-paint": [perfLevel, { maxNumericValue: lcpMax }],
        // CLS good = 0.1; tightening from 0.15 to 0.1 was the audit ask.
        "cumulative-layout-shift": [perfLevel, { maxNumericValue: 0.1 }],
        // INP good = 200ms. Lighthouse 10+ audit id.
        "interaction-to-next-paint": [perfLevel, { maxNumericValue: 200 }],
        // First Contentful Paint good = 1800ms.
        "first-contentful-paint": [perfLevel, { maxNumericValue: 1800 }],
        // Total Blocking Time good = 200ms (proxy for INP on lab runs).
        "total-blocking-time": [perfLevel, { maxNumericValue: 200 }],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};
