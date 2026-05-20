// @ts-check
const { test, expect } = require("@playwright/test");

const MGR = process.env.MANAGER_HOST || "manager.runmycampus.com:8000";

test.describe("AI Center + API Center surfaces", () => {
  test.skip(!process.env.E2E_LOGIN_USER, "Set E2E_LOGIN_USER/E2E_LOGIN_PASSWORD for live sweep");

  test("super AI center home resolves", async ({ page }) => {
    await page.goto(`http://${MGR}/super/ai-center/`);
    await expect(page.locator("h1")).toContainText(/AI Center/i);
  });

  test("api center dashboard link target", async ({ page }) => {
    await page.goto(`http://${MGR}/api-center/`);
    await expect(page.locator("body")).not.toContainText('href="#"');
  });
});
