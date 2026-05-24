/**
 * SFDP Phase 3 — sovereign financial local-global Playwright smoke (batch 1470).
 * Requires Django on VISUAL_QA_PORT with tenant finance routes.
 */
import { test, expect } from "@playwright/test";

const VIEWPORTS = [
  { width: 390, height: 844, name: "mobile" },
  { width: 768, height: 1024, name: "tablet" },
  { width: 1366, height: 768, name: "desktop" },
];

for (const vp of VIEWPORTS) {
  test(`payment readiness dashboard ${vp.name} no horizontal overflow`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    const base = process.env.VISUAL_QA_BASE_URL || "http://127.0.0.1:8000";
    await page.goto(`${base}/finance/payment-readiness/`, { waitUntil: "domcontentloaded" });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    expect(overflow).toBeFalsy();
  });
}
