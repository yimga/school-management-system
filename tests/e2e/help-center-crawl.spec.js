// @ts-check
// Help center + KB crawl (tenant + manager). Requires live Django + credentials.
// Run (Lane 2): npm run test:e2e:help-center:lane2
// Or: E2E_TENANT_HOST=gilead-school.runmycampus.com:8000 E2E_USERNAME=demo.admin E2E_PASSWORD=Test1234 npm run test:e2e:help-center

const { test, expect } = require("@playwright/test");

// Tenant uses canonical subdomain (see playwright.config.js host-resolver-rules).
const TENANT_HOST = process.env.E2E_TENANT_HOST || "gilead-school.runmycampus.com:8000";
const TENANT_BASE = `http://${TENANT_HOST.replace(/\/$/, "")}`;
const LOGIN_PATH = `${TENANT_BASE}/authentication/login/`;
const MANAGER_HOST = process.env.E2E_MANAGER_HOST || "manager.runmycampus.com:8000";
const MANAGER_BASE = `http://${MANAGER_HOST}`;

async function tenantLogin(page) {
  const username = process.env.E2E_USERNAME || "demo.admin";
  const password = process.env.E2E_PASSWORD || "Test1234";
  if (!username || !password) {
    test.skip();
    return false;
  }
  await page.goto(LOGIN_PATH);
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption("staff");
  }
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: /log in/i }).click();
  await page.waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), {
    timeout: 20000,
  });
  return true;
}

async function managerLogin(page) {
  const username = process.env.E2E_MANAGER_USERNAME || process.env.E2E_USERNAME || "admin";
  const password = process.env.E2E_MANAGER_PASSWORD || process.env.E2E_PASSWORD || "Sch00l_1234";
  if (!username || !password) {
    test.skip();
    return false;
  }
  await page.goto(`${MANAGER_BASE}/authentication/login/`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: /log in/i }).click();
  await page.waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), {
    timeout: 20000,
  });
  return true;
}

test("tenant help center loads and shows help content", async ({ page }) => {
  if (!(await tenantLogin(page))) return;
  const response = await page.goto(`${TENANT_BASE}/feedback/help/`);
  expect(response?.status()).toBeLessThan(400);
  await expect(page.locator("body")).toContainText(/help/i);
});

test("tenant KB home loads when route exists", async ({ page }) => {
  if (!(await tenantLogin(page))) return;
  const response = await page.goto(`${TENANT_BASE}/kb/`);
  if (response && response.status() === 404) {
    test.skip();
    return;
  }
  expect(response?.status()).toBeLessThan(400);
  await expect(page.locator("body")).toContainText(/knowledge|help|article/i);
});

test("manager help center hub loads", async ({ page }) => {
  if (!(await managerLogin(page))) return;
  const response = await page.goto(`${MANAGER_BASE}/help-center/`);
  expect(response?.status()).toBeLessThan(400);
  await expect(page.locator("body")).toContainText(/help|discover|knowledge/i);
});

test("manager KB home has AI panel contract markers", async ({ page }) => {
  if (!(await managerLogin(page))) return;
  const response = await page.goto(`${MANAGER_BASE}/kb/`);
  if (response && response.status() === 404) {
    test.skip();
    return;
  }
  expect(response?.status()).toBeLessThan(400);
  const panel = page.locator("[data-rmc-kb-ai-panel]");
  if (await panel.count()) {
    await expect(panel).toHaveAttribute("data-support-assistant-url", /.+/);
    await expect(panel.locator("#rmc-kb-ai-prompt")).toBeVisible();
  }
});
