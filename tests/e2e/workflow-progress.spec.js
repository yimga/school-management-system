// @ts-check
// Workflow Progress Bus — static + optional authenticated Playwright coverage (v4.01.20).

const fs = require("fs");
const { test, expect } = require("@playwright/test");
const {
  ensureManagerSession,
  MANAGER_BASE_URL,
  AUTH_STATE_PATH,
} = require("./helpers/manager-login");

// Browser: manager.runmycampus.com (host-resolver → 127.0.0.1 in playwright.config.js).
// APIRequest has no Chromium host map — call loopback with Host header instead.
const MGR_ORIGIN = MANAGER_BASE_URL.replace(/\/$/, "");
const MGR_PORT = process.env.VISUAL_QA_PORT || "8012";
const MGR_API_ORIGIN = `http://127.0.0.1:${MGR_PORT}`;

const MGR_HOST_HEADER = { Host: "manager.runmycampus.com" };

/** @param {import('@playwright/test').APIRequestContext} request @param {string} path */
async function managerGetOrSkip(request, path, extraHeaders = {}) {
  try {
    return await request.get(`${MGR_API_ORIGIN}${path}`, {
      headers: {
        Accept: "application/json",
        ...MGR_HOST_HEADER,
        ...extraHeaders,
      },
      failOnStatusCode: false,
      timeout: 8000,
    });
  } catch (_err) {
    test.skip(
      true,
      `Django not reachable at ${MGR_API_ORIGIN} (runserver on VISUAL_QA_PORT)`
    );
    return null;
  }
}

/** @param {import('@playwright/test').Page} page @param {Record<string, string>} [extra] */
async function managerApiHeaders(page, extra = {}) {
  const cookies = await page.context().cookies();
  const cookieHeader = cookies
    .filter((c) => String(c.value || "").trim())
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  return {
    Accept: "application/json",
    ...MGR_HOST_HEADER,
    ...(cookieHeader ? { Cookie: cookieHeader } : {}),
    ...extra,
  };
}

/** @param {import('@playwright/test').Page} page @param {string} path @param {Record<string, string>} [extra] */
async function managerApiGet(page, path, extra = {}) {
  return page.request.get(`${MGR_API_ORIGIN}${path}`, {
    headers: await managerApiHeaders(page, extra),
    failOnStatusCode: false,
  });
}

/** @param {import('@playwright/test').Page} page @param {string} path @param {object} opts */
async function managerApiPost(page, path, opts = {}) {
  return page.request.post(`${MGR_API_ORIGIN}${path}`, {
    ...opts,
    headers: await managerApiHeaders(page, opts.headers || {}),
    failOnStatusCode: false,
  });
}

test.describe("Workflow progress — unauthenticated smoke", () => {
  test("workflow-progress.css bundle is reachable", async ({ page }) => {
    const resp = await page.goto(`${MGR_ORIGIN}/static/css/rmc-workflow-progress.css`);
    expect([200, 304]).toContain(resp.status());
    const body = await page.content();
    expect(body).toContain(".rmc-wfp-chip");
    expect(body).toContain("rmc-wfp-card");
  });

  test("workflow-track-headers.js ships opt-in header contract", async ({ page }) => {
    const resp = await page.goto(`${MGR_ORIGIN}/static/js/rmc-workflow-track-headers.js`);
    expect([200, 304]).toContain(resp.status());
    const body = await page.content();
    expect(body).toContain("X-RMC-Workflow-Track");
    expect(body).toContain("__rmcWorkflowTrackHeadersMounted");
  });

  test("active runs API returns 401 when anonymous", async ({ request }) => {
    const resp = await managerGetOrSkip(request, "/platform-runtime/workflow-progress/active/");
    if (!resp) return;
    expect(resp.status()).toBe(401);
  });

  test("SSE stream returns 401 when anonymous", async ({ request }) => {
    const resp = await managerGetOrSkip(request, "/platform-runtime/workflow-progress/stream/", {
      Accept: "text/event-stream",
    });
    if (!resp) return;
    expect(resp.status()).toBe(401);
  });

  test("flight-deck static bundle is reachable", async ({ page }) => {
    const resp = await page.goto(`${MGR_ORIGIN}/static/js/rmc-workflow-flight-deck.js`);
    expect([200, 304]).toContain(resp.status());
    const body = await page.content();
    expect(body).toContain("rmc-wfp-flight-deck");
  });

  test("flight-deck JSON returns 401 when anonymous", async ({ request }) => {
    const resp = await managerGetOrSkip(
      request,
      "/platform-runtime/workflow-progress/flight-deck.json"
    );
    if (!resp) return;
    expect(resp.status()).toBe(401);
  });
});

test.describe("Workflow progress — operator shell (authenticated)", () => {
  test.skip(!process.env.E2E_LOGIN_USER, "Set E2E_LOGIN_USER + E2E_LOGIN_PASSWORD for live sweep");

  test.beforeAll(() => {
    if (!fs.existsSync(AUTH_STATE_PATH)) {
      throw new Error(
        `Missing ${AUTH_STATE_PATH}. Run: npm run test:e2e:workflow-progress ` +
          "(exports storage) or python scripts/export_manager_playwright_storage.py"
      );
    }
  });

  test.use({ storageState: AUTH_STATE_PATH });

  /** @param {import('@playwright/test').Page} page */
  async function ensureOperatorSession(page) {
    await ensureManagerSession(page, {
      username: process.env.E2E_LOGIN_USER,
      password: process.env.E2E_LOGIN_PASSWORD,
    });
  }

  test("manager shell loads track-headers before progress chip script", async ({ page }) => {
    await ensureOperatorSession(page);
    await page.goto(`${MGR_ORIGIN}/super/`, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    const html = await page.content();
    const headersIdx = html.indexOf("rmc-workflow-track-headers.js");
    const progressIdx = html.indexOf("rmc-workflow-progress.js");
    expect(headersIdx).toBeGreaterThan(-1);
    expect(progressIdx).toBeGreaterThan(-1);
    expect(
      headersIdx < progressIdx,
      "track-headers must appear before workflow-progress.js in HTML"
    ).toBeTruthy();
  });

  test("workflow progress chip or assist-dock slot is present on super landing", async ({
    page,
  }) => {
    await ensureOperatorSession(page);
    await page.goto(`${MGR_ORIGIN}/super/`, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    const chip = page.locator("#rmc-wfp-chip, [data-rmc-assist-slot-id='workflow-progress']");
    await expect(chip.first()).toBeAttached({ timeout: 30000 });
  });

  test("inline workflow strip mount point exists on control plane shell", async ({ page }) => {
    await ensureOperatorSession(page);
    await page.goto(`${MGR_ORIGIN}/super/`, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    const strip = page.locator("[data-rmc-wfp-inline-strip]");
    if ((await strip.count()) === 0) {
      test.skip(true, "inline strip not on this landing — optional chrome");
    }
    await expect(strip.first()).toBeAttached();
  });

  /** @param {import('@playwright/test').Page} page */
  async function csrfFromPage(page) {
    const cookies = await page.context().cookies();
    const hit =
      cookies.find((c) => c.name === "rmc_manager_csrftoken") ||
      cookies.find((c) => c.name === "csrftoken");
    return hit ? hit.value : "";
  }

  test("progress bar advances during staff e2e demo run", async ({ page }) => {
    await ensureOperatorSession(page);
    const csrf = await csrfFromPage(page);
    const start = await managerApiPost(
      page,
      "/platform-runtime/workflow-progress/e2e-demo/start/",
      {
        headers: {
          "X-CSRFToken": csrf,
          Referer: `${MGR_ORIGIN}/super/`,
        },
      }
    );
    if (start.status() === 403) {
      test.skip(true, "e2e demo disabled — set DEBUG=1 or RMC_ALLOW_WORKFLOW_E2E_DEMO=1");
    }
    expect(start.ok(), `demo start HTTP ${start.status()}`).toBeTruthy();
    const started = await start.json();
    const runId = started.run_id;
    expect(runId).toBeTruthy();

    let sawProgress = false;
    for (let attempt = 0; attempt < 24; attempt += 1) {
      const active = await managerApiGet(page, "/platform-runtime/workflow-progress/active/");
      if (active.ok()) {
        const data = await active.json();
        const rows = data.runs || data.active || [];
        const run = rows.find((row) => row.id === runId);
        if (run && typeof run.progress_percent === "number" && run.progress_percent >= 15) {
          sawProgress = true;
          break;
        }
      }
      await page.waitForTimeout(400);
    }
    expect(sawProgress, "active API never reported demo run progress").toBeTruthy();

    await page.goto(`${MGR_ORIGIN}/super/`, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    const chip = page.locator("#rmc-wfp-chip");
    if ((await chip.count()) === 0) {
      test.skip(true, "workflow progress chip not mounted on super landing in this build");
    }
    await chip.click({ timeout: 20000 });
    const fill = page.locator(".rmc-wfp-bar__fill").first();
    if ((await fill.count()) === 0) {
      return;
    }
    await expect(fill).toBeVisible({ timeout: 15000 });
    const width = await fill.evaluate(
      (el) => el.style.width || window.getComputedStyle(el).width
    );
    expect(width).not.toMatch(/^0(%|px)?$/);
  });

  test("Flight Deck mission control page loads for staff", async ({ page }) => {
    await ensureOperatorSession(page);
    const resp = await page.goto(`${MGR_ORIGIN}/platform-runtime/workflow-progress/flight-deck/`, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    expect(resp && resp.status() < 500, `flight-deck HTTP ${resp?.status()}`).toBeTruthy();
    await expect(page.locator("#rmc-wfp-flight-deck")).toBeAttached({
      timeout: 30000,
    });
    const json = await managerApiGet(
      page,
      "/platform-runtime/workflow-progress/flight-deck.json"
    );
    expect(json.ok(), `flight-deck.json HTTP ${json.status()}`).toBeTruthy();
    const payload = await json.json();
    expect(payload).toHaveProperty("active");
    expect(Array.isArray(payload.active)).toBeTruthy();
  });
});
