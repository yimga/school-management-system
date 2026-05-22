/**
 * GEOS-99 batch 1387: axe serious/critical 0 on help + AI Center routes.
 * Requires live server: VISUAL_QA_PORT=8014 npm run test:e2e:help-ai-center-a11y
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const BASE = process.env.VISUAL_QA_BASE_URL || "http://127.0.0.1:8014";

test.describe("Help + AI Center accessibility (GEOS-99)", () => {
  test.skip(!process.env.GEOS_A11Y_E2E, "Set GEOS_A11Y_E2E=1 with Django seeded on BASE");

  test("manager help hub has no serious/critical axe violations", async ({ page }) => {
    await page.goto(`${BASE}/help-center/`, { waitUntil: "domcontentloaded" });
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical"
    );
    expect(serious, JSON.stringify(serious, null, 2)).toHaveLength(0);
  });

  test("AI gateway console route loads for axe scan", async ({ page }) => {
    await page.goto(`${BASE}/super/ai-gateway-console/`, { waitUntil: "domcontentloaded" });
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical"
    );
    expect(serious, JSON.stringify(serious, null, 2)).toHaveLength(0);
  });
});
