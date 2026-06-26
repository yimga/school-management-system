// @ts-check
/** Metric #2 — axe serious/critical = 0 on tenant login + parent portal surfaces. */
const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

function loadLoginTenant(baseUrl) {
  if (baseUrl) {
    process.env.TENANT_E2E_BASE_URL = baseUrl.replace(/\/$/, "");
    process.env.PLAYWRIGHT_TENANT_BASE_URL = process.env.TENANT_E2E_BASE_URL;
  }
  delete require.cache[require.resolve("./helpers/tenant-login")];
  return require("./helpers/tenant-login");
}

async function assertNoSeriousAxe(page, label) {
  if (process.env.SKIP_AXE === "1") {
    return;
  }
  const { violations } = await new AxeBuilder({ page }).analyze();
  const blocking = violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious"
  );
  expect(
    blocking,
    `${label}: ${blocking.map((v) => v.id).join(", ") || "none"}`
  ).toEqual([]);
}

test.describe("Tenant shell accessibility (axe)", () => {
  test("login page has no serious axe violations", async ({ page }, testInfo) => {
    const tenantBase = String(testInfo.project.use.baseURL || "").replace(/\/$/, "");
    await page.goto(`${tenantBase}/authentication/login/`, {
      waitUntil: "domcontentloaded",
      timeout: 120000,
    });
    await assertNoSeriousAxe(page, "tenant-login");
  });

  test("parent portal has no serious axe violations", async ({ page }, testInfo) => {
    const tenantBase = String(testInfo.project.use.baseURL || "").replace(/\/$/, "");
    const { loginTenant } = loadLoginTenant(tenantBase);
    await loginTenant(page, { username: "demo.parent" });
    await page.goto(`${tenantBase}/portal/parent/`, {
      waitUntil: "domcontentloaded",
      timeout: 120000,
    });
    await assertNoSeriousAxe(page, "parent-portal");
  });
});
