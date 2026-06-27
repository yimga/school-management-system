/** Tenant shell Lighthouse CI — login + portal entry surfaces (metric 2/17). */
const strictAPlus = process.env.LHCI_TENANT_STRICT === "1";
const perfLevel = strictAPlus ? "error" : "warn";
const perfMin = strictAPlus ? 0.98 : 0.82;
const lcpMax = strictAPlus ? 2500 : 3500;
const tenantHost =
  (process.env.LHCI_TENANT_HOST || "demo-school.runmycampus.com").trim();
const tenantPort = (process.env.VISUAL_QA_TENANT_PHASE_PORT || process.env.VISUAL_QA_PORT || "8124").trim();

const primary = (
  process.env.LHCI_TENANT_URL ||
  `http://127.0.0.1:${tenantPort}/authentication/login/`
).trim();
const extrasRaw = (process.env.LHCI_TENANT_URLS_EXTRA || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

function autoTenantExtras(p) {
  try {
    const u = new URL(p);
    const base = u.origin + u.pathname.replace(/\/authentication\/login\/?$/, "");
    return [
      `${base}/portal/`,
      `${base}/portal/parent/`,
      `${base}/portal/teacher/`,
      `${base}/offline/`,
    ];
  } catch {
    return [];
  }
}

const autoOn = process.env.LHCI_TENANT_AUTO_EXTRAS !== "0";
const autoUrls = autoOn ? autoTenantExtras(primary) : [];
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
      settings: {
        extraHeaders: { Host: tenantHost },
      },
      chromeFlags: [
        "--headless=new",
        "--host-rules=MAP *.runmycampus.com 127.0.0.1, MAP runmycampus.com 127.0.0.1",
      ],
    },
    assert: {
      assertions: {
        "categories:performance": [perfLevel, { minScore: perfMin }],
        "categories:accessibility": [perfLevel, { minScore: strictAPlus ? 0.98 : 0.9 }],
        "categories:best-practices": [perfLevel, { minScore: strictAPlus ? 0.98 : 0.9 }],
        "categories:seo": [perfLevel, { minScore: strictAPlus ? 0.98 : 0.85 }],
        "largest-contentful-paint": [perfLevel, { maxNumericValue: lcpMax }],
        "cumulative-layout-shift": [perfLevel, { maxNumericValue: 0.1 }],
        "total-blocking-time": [perfLevel, { maxNumericValue: 300 }],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};
