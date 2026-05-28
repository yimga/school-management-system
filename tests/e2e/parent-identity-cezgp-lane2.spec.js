// @ts-check
/**
 * CEZGP Lane 2 — parent password-reset discoverability on tenant login.
 *
 * Use canonical tenant subdomain (not /t/<slug>/ — Chromium host-rules refuse /t/<slug>).
 *
 * Local:
 *   MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8000
 *   python manage.py ensure_demo_environment --school-slug=demo-school
 *   PLAYWRIGHT_TENANT_BASE_URL=http://demo-school.runmycampus.com:8000 \\
 *     npx playwright test tests/e2e/parent-identity-cezgp-lane2.spec.js
 */
const { test, expect } = require("@playwright/test");

const TENANT_BASE = (
  process.env.PLAYWRIGHT_TENANT_BASE_URL ||
  process.env.PLAYWRIGHT_BASE_URL ||
  "http://demo-school.runmycampus.com:8000"
).replace(/\/$/, "");

const LOGIN_PATH =
  process.env.TENANT_LOGIN_PATH || "/authentication/login/";

test.use({ baseURL: TENANT_BASE });

test.describe("CEZGP Lane 2 parent identity", () => {
  test("password reset form is reachable from tenant login", async ({ page }) => {
    const res = await page.goto(LOGIN_PATH, {
      waitUntil: "domcontentloaded",
      timeout: 45000,
    });
    expect(res?.status() ?? 500).toBeLessThan(500);
    const forgot = page.locator('[data-rmc-parent-password-reset="1"]');
    await expect(forgot).toBeVisible({ timeout: 15000 });
    const resetHref = await forgot.getAttribute("href");
    expect(resetHref || "").toMatch(/password_reset/);
    await page.goto(resetHref || "/authentication/password_reset/", {
      waitUntil: "domcontentloaded",
      timeout: 45000,
    });
    await expect(page).toHaveURL(/password_reset/);
    await expect(page.locator("#id_email, input[name='email']")).toBeVisible();
  });
});
