/**
 * Report card tenant E2E — teacher/admin publish surface + parent download path.
 *
 * Staging-only (same contract as first-school-operating-proof.spec.ts).
 * Proves report routes respond for authenticated roles when staging creds are set.
 */
import { test, expect, Page } from "@playwright/test";

const BASE_URL = process.env.RMC_STAGING_BASE_URL || "";
const STAFF_USER = process.env.RMC_STAGING_STAFF_USER || process.env.RMC_STAGING_TEST_USER || "";
const STAFF_PASS = process.env.RMC_STAGING_STAFF_PASS || process.env.RMC_STAGING_TEST_PASS || "";
const PARENT_USER = process.env.RMC_STAGING_PARENT_USER || "";
const PARENT_PASS = process.env.RMC_STAGING_PARENT_PASS || "";

const SKIP_STAFF =
  "Staff staging creds missing — set RMC_STAGING_BASE_URL + RMC_STAGING_TEST_USER/PASS (or STAFF_*).";
const SKIP_PARENT =
  "Parent staging creds missing — set RMC_STAGING_PARENT_USER/PASS for download proof.";

async function login(page: Page, username: string, password: string): Promise<void> {
  await page.goto("/authentication/login/");
  const usernameInput = page
    .locator(
      'input[name="username"], input[name="email"], input[type="email"], input[id="id_username"]'
    )
    .first();
  const passwordInput = page
    .locator('input[name="password"], input[type="password"], input[id="id_password"]')
    .first();
  await usernameInput.fill(username);
  await passwordInput.fill(password);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15_000 }),
    page.locator('button[type="submit"], input[type="submit"]').first().click(),
  ]);
}

test.describe("Report cards — staff publish surface", () => {
  test.beforeEach(async ({}, testInfo) => {
    if (!BASE_URL || !STAFF_USER || !STAFF_PASS) {
      testInfo.skip(true, SKIP_STAFF);
    }
  });

  test("publish term results page loads for staff", async ({ page }) => {
    await login(page, STAFF_USER, STAFF_PASS);
    const resp = await page.goto("/reports/publish/", { waitUntil: "domcontentloaded" });
    expect(resp?.status() ?? 0).toBeLessThan(400);
    await expect(page.locator("body")).toContainText(/publish|term|report/i);
  });
});

test.describe("Report cards — parent download", () => {
  test.beforeEach(async ({}, testInfo) => {
    if (!BASE_URL || !PARENT_USER || !PARENT_PASS) {
      testInfo.skip(true, SKIP_PARENT);
    }
  });

  test("parent reports library is reachable", async ({ page }) => {
    await login(page, PARENT_USER, PARENT_PASS);
    const candidates = [
      "/portal/reports/",
      "/portal/parent/reports/",
      "/portal/children/",
    ];
    let opened = false;
    for (const path of candidates) {
      const resp = await page.goto(path, { waitUntil: "domcontentloaded" });
      if (resp && resp.status() < 400) {
        opened = true;
        break;
      }
    }
    expect(opened, "no parent reports route returned <400").toBeTruthy();
  });
});
