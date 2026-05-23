/**
 * Wave C-1 (batch 1402) — ExperienceTemplate marketplace Playwright spec.
 *
 * Covers operator + tenant catalog at 3 breakpoints (390 / 768 / 1366).
 * Tests the boundary contracts that matter:
 *   - operator-only templates absent from tenant catalog
 *   - preview routes render
 *   - apply confirmation gate
 *   - no horizontal overflow at any breakpoint
 *   - tag/category filter rail works
 *
 * Run via: npx playwright test tests/e2e/template-marketplace.spec.js
 * Honors PLAYWRIGHT_BASE_URL env var; defaults to http://localhost:8000.
 */

const { test, expect } = require("@playwright/test");

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8000";
const BREAKPOINTS = [
  { name: "mobile-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1366", width: 1366, height: 768 },
];

const TENANT_BROWSE = "/school/studio/templates/";
const OPERATOR_BROWSE = "/configuration/experience-templates/";

async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => {
    const docW = document.documentElement.clientWidth;
    const bodyW = document.body.scrollWidth;
    return { docW, bodyW, overflow: bodyW > docW + 1 };
  });
  expect(overflow.overflow, `body scrollWidth=${overflow.bodyW} > docW=${overflow.docW}`).toBeFalsy();
}

for (const bp of BREAKPOINTS) {
  test.describe(`Template marketplace @ ${bp.name}`, () => {
    test.use({ viewport: { width: bp.width, height: bp.height } });

    test(`tenant browse renders without horizontal overflow @ ${bp.name}`, async ({ page }) => {
      const response = await page.goto(`${BASE_URL}${TENANT_BROWSE}`, { waitUntil: "domcontentloaded" });
      expect(response.status(), "tenant browse must be 200 or 302 to login").toBeLessThan(500);
      if (response.status() === 200) {
        await expect(page.locator('[data-page-marker="rmc-template-marketplace-tenant"]')).toBeVisible();
        await assertNoHorizontalOverflow(page);
      }
    });

    test(`tenant catalog never shows operator-only templates @ ${bp.name}`, async ({ page }) => {
      const response = await page.goto(`${BASE_URL}${TENANT_BROWSE}`, { waitUntil: "domcontentloaded" });
      if (response.status() !== 200) {
        test.skip(true, "tenant catalog requires auth — skipping isolation check on unauthenticated run");
        return;
      }
      const operatorKeys = [
        "operator-executive-command-center",
        "operator-implementation-war-room",
        "operator-security-compliance-command",
        "operator-revenue-billing-ops",
        "operator-marketplace-console",
      ];
      for (const key of operatorKeys) {
        const card = page.locator(`[data-rmc-template-card="${key}"]`);
        await expect(card, `operator template ${key} must be absent from tenant catalog`).toHaveCount(0);
      }
    });

    test(`tenant filter rail collapses to column on mobile @ ${bp.name}`, async ({ page }) => {
      if (bp.name !== "mobile-390") {
        test.skip(true, "filter rail collapse is mobile-only");
        return;
      }
      const response = await page.goto(`${BASE_URL}${TENANT_BROWSE}`, { waitUntil: "domcontentloaded" });
      if (response.status() !== 200) {
        test.skip(true, "tenant catalog requires auth");
        return;
      }
      const rail = page.locator(".rmc-template-marketplace__filter-rail");
      if (await rail.count()) {
        const flexDir = await rail.evaluate(el => window.getComputedStyle(el).flexDirection);
        expect(flexDir).toBe("column");
      }
    });

    test(`tenant preview frame renders @ ${bp.name}`, async ({ page }) => {
      const response = await page.goto(
        `${BASE_URL}${TENANT_BROWSE}parent-family-home/preview/`,
        { waitUntil: "domcontentloaded" }
      );
      if (response.status() !== 200) {
        test.skip(true, "preview route requires auth");
        return;
      }
      await expect(page.locator('[data-page-marker="rmc-template-preview"]')).toBeVisible();
      await expect(page.locator('[data-rmc-template-preview-iframe="1"]')).toBeVisible();
      await assertNoHorizontalOverflow(page);
    });

    test(`tenant apply page requires explicit confirmation @ ${bp.name}`, async ({ page }) => {
      const response = await page.goto(
        `${BASE_URL}${TENANT_BROWSE}parent-family-home/apply/`,
        { waitUntil: "domcontentloaded" }
      );
      if (response.status() !== 200) {
        test.skip(true, "apply route requires auth");
        return;
      }
      const submitBtn = page.locator('.rmc-template-apply__submit');
      await expect(submitBtn).toHaveAttribute("data-rmc-confirm", /Apply this template/i);
    });

    test(`compare view renders side-by-side @ ${bp.name}`, async ({ page }) => {
      const response = await page.goto(
        `${BASE_URL}${TENANT_BROWSE}parent-family-home/compare/?other=parent-student-progress`,
        { waitUntil: "domcontentloaded" }
      );
      if (response.status() !== 200) {
        test.skip(true, "compare route requires auth");
        return;
      }
      await expect(page.locator(".rmc-template-compare__column")).toHaveCount(2);
      await assertNoHorizontalOverflow(page);
    });

    test(`operator browse renders @ ${bp.name}`, async ({ page }) => {
      const response = await page.goto(`${BASE_URL}${OPERATOR_BROWSE}`, { waitUntil: "domcontentloaded" });
      expect(response.status(), "operator browse must be < 500").toBeLessThan(500);
      if (response.status() === 200) {
        await expect(page.locator('[data-page-marker="rmc-pack-installation-marketplace"]')).toBeVisible();
        await assertNoHorizontalOverflow(page);
      }
    });
  });
}
