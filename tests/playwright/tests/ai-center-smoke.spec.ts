/**
 * AI Center browser smoke (plan §5.3 optional Playwright).
 *
 * Types a question on AI Center and asserts visible answer text when staging
 * creds are configured. Skips cleanly without RMC_STAGING_* env vars.
 */
import { test, expect, Page } from "@playwright/test";

const BASE_URL = process.env.RMC_STAGING_BASE_URL || "";
const TEST_USER = process.env.RMC_STAGING_TEST_USER || "";
const TEST_PASS = process.env.RMC_STAGING_TEST_PASS || "";

const SKIP_REASON =
  "Staging creds not set — define RMC_STAGING_BASE_URL, RMC_STAGING_TEST_USER, RMC_STAGING_TEST_PASS.";

test.beforeEach(async ({}, testInfo) => {
  if (!BASE_URL || !TEST_USER || !TEST_PASS) {
    testInfo.skip(true, SKIP_REASON);
  }
});

async function login(page: Page): Promise<void> {
  await page.goto("/authentication/login/");
  const usernameInput = page
    .locator(
      'input[name="username"], input[name="email"], input[type="email"], input[id="id_username"]'
    )
    .first();
  const passwordInput = page
    .locator('input[name="password"], input[type="password"], input[id="id_password"]')
    .first();
  await usernameInput.waitFor({ state: "visible" });
  await usernameInput.fill(TEST_USER);
  await passwordInput.fill(TEST_PASS);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15_000 }),
    page.locator('button[type="submit"], input[type="submit"]').first().click(),
  ]);
}

test.describe("AI Center smoke", () => {
  test("guided assistant returns visible answer text", async ({ page }) => {
    await login(page);
    await page.goto("/siteconfig/ai-center/");
    await expect(page.locator("[data-rmc-ai-center]")).toBeVisible();
    const query = page.locator("[data-rmc-ai-query]").first();
    await query.fill("Where is district interop configured?");
    await page.locator("[data-rmc-ai-run]").first().click();
    const out = page.locator("[data-rmc-ai-out]").first();
    await expect(out).toBeVisible({ timeout: 30_000 });
    const text = (await out.textContent()) || "";
    expect(text.length).toBeGreaterThan(40);
    expect(text.toLowerCase()).not.toContain("syntaxerror");
  });
});
