import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for RunMyCampus integration tests.
 *
 * Required env vars (read at runtime):
 *   RMC_STAGING_BASE_URL    e.g. https://gilead-school.staging.runmycampus.com
 *   RMC_STAGING_TEST_USER   email or username of the seeded test user
 *   RMC_STAGING_TEST_PASS   password for that user
 *
 * Without these, the tests skip with a clear message — they will never run
 * against production or break locally for someone who has not configured
 * staging credentials.
 */
const baseURL = process.env.RMC_STAGING_BASE_URL || "";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,            // lifecycle steps depend on order
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,                      // single-tenant test — no parallelism
  reporter: process.env.CI
    ? [["github"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: baseURL || undefined,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: process.env.CI ? "retain-on-failure" : "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
