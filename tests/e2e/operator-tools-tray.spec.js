// @ts-check
/** Operator Tools edge-tray — live manager smoke (HTTP + optional browser tray open). */

const { test, expect } = require("@playwright/test");
const {
  ensureManagerSession,
  MANAGER_BASE_URL,
} = require("./helpers/manager-login");

const MGR_PORT = process.env.VISUAL_QA_PORT || "8012";
const MGR_API = `http://127.0.0.1:${MGR_PORT}`;
const MGR_HOST = { Host: "manager.runmycampus.com" };

test.describe("Operator Tools edge-tray", () => {
  test.setTimeout(180000);

  test("manager /super/ HTML ships operator tools island", async ({ request }) => {
    let ready;
    try {
      ready = await request.get(`${MGR_API}/ready/`, {
        headers: MGR_HOST,
        timeout: 8000,
      });
    } catch (_err) {
      test.skip(true, `Django not reachable at ${MGR_API}`);
      return;
    }
    if (!ready || !ready.ok()) {
      test.skip(true, `/ready/ not OK on ${MGR_API}`);
      return;
    }

    const loginPage = await request.get(`${MGR_API}/authentication/login/`, {
      headers: MGR_HOST,
    });
    expect(loginPage.ok()).toBeTruthy();
    const loginHtml = await loginPage.text();
    const csrfMatch = loginHtml.match(/name="csrfmiddlewaretoken"\s+value="([^"]+)"/);
    expect(csrfMatch).toBeTruthy();
    const csrf = csrfMatch[1];
    const user = process.env.E2E_LOGIN_USER || "admin";
    const pass = process.env.E2E_LOGIN_PASSWORD || "Sch00l_1234";

    const loginPost = await request.post(`${MGR_API}/authentication/login/`, {
      headers: {
        ...MGR_HOST,
        "Content-Type": "application/x-www-form-urlencoded",
        Referer: `${MGR_API}/authentication/login/`,
      },
      form: {
        username: user,
        password: pass,
        csrfmiddlewaretoken: csrf,
        next: "/super/",
      },
    });
    expect([200, 302]).toContain(loginPost.status());

    const dash = await request.get(`${MGR_API}/super/`, {
      headers: MGR_HOST,
      timeout: 120000,
    });
    expect(dash.status()).toBe(200);
    const body = await dash.text();
    expect(body).toContain('id="page-data-rmc-operator-tools"');
    expect(body).toContain("rmc-operator-tools-tray.js");
    expect(body).not.toContain('data-rmc-back-to-top-policy="always"');
  });

  test("tenant backend ships tenant tools island", async ({ request }) => {
    const tenantSlug = process.env.TENANT_SWEEP_SLUG || "apple-class-qa";
    const tenantHost = {
      Host: process.env.VISUAL_QA_TENANT_HOST || `${tenantSlug}.runmycampus.com`,
    };
    let ready;
    try {
      ready = await request.get(`${MGR_API}/ready/`, {
        headers: tenantHost,
        timeout: 8000,
      });
    } catch (_err) {
      test.skip(true, `Django not reachable at ${MGR_API}`);
      return;
    }
    if (!ready || !ready.ok()) {
      test.skip(true, `/ready/ not OK on ${MGR_API}`);
      return;
    }

    const loginPath = `/authentication/login/`;
    const portalPath = `/portal/teacher/`;
    const tenantUser = process.env.TENANT_SMOKE_USER || "demo.teacher";
    const tenantPass = process.env.TENANT_SMOKE_PASSWORD || "Test1234";
    const loginPage = await request.get(`${MGR_API}${loginPath}`, {
      headers: tenantHost,
    });
    if (!loginPage.ok()) {
      test.skip(true, `tenant login page not OK for ${tenantSlug}`);
      return;
    }
    const loginHtml = await loginPage.text();
    const csrfMatch = loginHtml.match(/name="csrfmiddlewaretoken"\s+value="([^"]+)"/);
    if (csrfMatch) {
      const csrf = csrfMatch[1];
      await request.post(`${MGR_API}${loginPath}`, {
        headers: {
          ...tenantHost,
          "Content-Type": "application/x-www-form-urlencoded",
          Referer: `${MGR_API}${loginPath}`,
        },
        form: {
          username: tenantUser,
          password: tenantPass,
          csrfmiddlewaretoken: csrf,
          next: portalPath,
        },
      });
    }

    const portal = await request.get(`${MGR_API}${portalPath}`, {
      headers: tenantHost,
      timeout: 120000,
    });
    if (portal.status() !== 200) {
      test.skip(true, `tenant portal not 200 for ${tenantSlug}`);
      return;
    }
    const body = await portal.text();
    expect(body).toContain('id="page-data-rmc-tenant-tools"');
    expect(body).toContain("rmc-operator-tools-tray.js");
    expect(body).not.toContain('id="page-data-rmc-operator-tools"');
    expect(body).not.toContain('data-rmc-back-to-top-policy="always"');
  });

  test("browser opens Tools edge tab on tenant backend", async ({ page, request }) => {
    const tenantSlug = process.env.TENANT_SLUG || "demo-school";
    const port = process.env.VISUAL_QA_PORT || "8012";
    const api = `http://127.0.0.1:${port}`;
    const tenantHost = {
      Host: process.env.VISUAL_QA_TENANT_HOST || `${tenantSlug}.runmycampus.com`,
    };
    let ready;
    try {
      ready = await request.get(`${api}/ready/`, { headers: tenantHost, timeout: 8000 });
    } catch (_err) {
      test.skip(true, `Django not reachable at ${api}`);
      return;
    }
    if (!ready || !ready.ok()) {
      test.skip(true, `/ready/ not OK on ${api}`);
      return;
    }

    const { loginTenant, TENANT_BASE_URL } = require("./helpers/tenant-login.js");
    const user = process.env.TENANT_SWEEP_USER || `${process.env.TENANT_DEMO_USERNAME_PREFIX || "demo"}.admin`;
    const pass = process.env.TENANT_SWEEP_PASSWORD || "Test1234";
    await loginTenant(page, { username: user, password: pass });
    await page.goto(`${TENANT_BASE_URL}/authentication/backend/`, {
      waitUntil: "domcontentloaded",
      timeout: 120000,
    });
    await expect(page.locator("#page-data-rmc-tenant-tools")).toBeAttached({ timeout: 60000 });
    const tab = page.locator(".rmc-operator-tools__edge-tab");
    await expect(tab).toBeVisible({ timeout: 60000 });
    await tab.click();
    const tray = page.locator("#rmcOperatorToolsTray");
    await expect(tray).toHaveAttribute("aria-hidden", "false");
    const hasContent = page.locator(
      ".rmc-operator-tools__group, [data-rmc-tools-tray-empty], [data-rmc-assist-slot-id]"
    );
    await expect(hasContent.first()).toBeVisible();
  });

  test("browser opens Tools edge tab on /super/", async ({ page }) => {
    test.skip(
      process.env.RMC_OPERATOR_TOOLS_E2E_BROWSER !== "1",
      "Set RMC_OPERATOR_TOOLS_E2E_BROWSER=1 when TOTP is seeded for E2E user"
    );
    await ensureManagerSession(page);
    await page.goto(`${MANAGER_BASE_URL.replace(/\/$/, "")}/super/`, {
      waitUntil: "domcontentloaded",
      timeout: 120000,
    });
    const config = page.locator("#page-data-rmc-operator-tools");
    await expect(config).toBeAttached({ timeout: 60000 });
    const tab = page.locator(".rmc-operator-tools__edge-tab");
    await expect(tab).toBeVisible({ timeout: 60000 });
    await tab.click();
    await expect(page.locator(".rmc-operator-tools__tray")).toBeVisible();
  });
});
