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
        "categories:performance": [perfLevel, { minScore: perfMin }],
        "largest-contentful-paint": [perfLevel, { maxNumericValue: lcpMax }],
        "cumulative-layout-shift": [perfLevel, { maxNumericValue: 0.15 }],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};
