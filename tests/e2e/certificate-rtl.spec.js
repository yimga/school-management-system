// @ts-check
/**
 * Metric 21 — certificate RTL (ar / he / fa).
 * Loads Django-rendered fixtures from disk into Chromium (no Django webServer).
 * Fixtures regenerated via:
 *   python -c "… write_rtl_e2e_fixtures('tests/e2e/fixtures')"
 *
 * Run: npm run test:e2e:certificate-rtl
 */
const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const FIXTURE_DIR = path.resolve(__dirname, "fixtures");

const LOCALES = [
  { code: "ar", file: "certificate-rtl-ar.html", sample: "شهادة" },
  { code: "he", file: "certificate-rtl-he.html", sample: "תעודת" },
  { code: "fa", file: "certificate-rtl-fa.html", sample: "گواهینامه" },
];

async function horizontalOverflowPx(page) {
  return page.evaluate(() =>
    Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  );
}

test.describe("certificate document — RTL locales", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    serviceWorkers: "block",
  });

  for (const locale of LOCALES) {
    test(`${locale.code}: dir=rtl, native title, no horizontal bleed`, async ({
      page,
    }) => {
      const html = fs.readFileSync(path.join(FIXTURE_DIR, locale.file), "utf8");
      expect(html.includes('dir="rtl"'), `${locale.code} fixture has dir=rtl`).toBe(true);

      await page.setContent(html, { waitUntil: "domcontentloaded" });

      const dir = await page.evaluate(
        () => document.documentElement.getAttribute("dir") || "",
      );
      const lang = await page.evaluate(
        () => document.documentElement.getAttribute("lang") || "",
      );
      expect(dir, `${locale.code} <html dir>`).toBe("rtl");
      expect(lang, `${locale.code} <html lang>`).toBe(locale.code);

      const title = page.locator("[data-rmc-cert-title]");
      await expect(title).toBeVisible();
      await expect(title).toContainText(locale.sample);
      await expect(title).not.toHaveText("Certificate of Achievement");

      const certDir = await page
        .locator("article.rmc-certificate")
        .getAttribute("data-rmc-cert-dir");
      expect(certDir).toBe("rtl");

      const overflow = await horizontalOverflowPx(page);
      expect(overflow, `${locale.code} horizontal overflow px`).toBeLessThanOrEqual(8);
    });
  }
});
