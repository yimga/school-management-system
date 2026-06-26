// @ts-check
/**
 * Metric #4 — parent views published grades + PDF hash verifies on tenant shell.
 * Requires seed_report_card_e2e (run via playwright tenant webServer).
 */
const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");

const FIXTURE_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "var",
  "e2e_report_card_fixture.json"
);

function loadLoginTenant(baseUrl) {
  if (baseUrl) {
    process.env.TENANT_E2E_BASE_URL = baseUrl.replace(/\/$/, "");
    process.env.PLAYWRIGHT_TENANT_BASE_URL = process.env.TENANT_E2E_BASE_URL;
  }
  delete require.cache[require.resolve("./helpers/tenant-login")];
  return require("./helpers/tenant-login");
}

function readFixture() {
  if (!fs.existsSync(FIXTURE_PATH)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(FIXTURE_PATH, "utf8"));
}

test.describe("Report card — parent view + hash verify", () => {
  test("parent sees grade band and PDF hash verifies", async ({ page }, testInfo) => {
    const fixture = readFixture();
    test.skip(!fixture, "Missing var/e2e_report_card_fixture.json — run seed_report_card_e2e");

    const tenantBase = String(testInfo.project.use.baseURL || "").replace(/\/$/, "");
    const { loginTenant } = loadLoginTenant(tenantBase);

    await loginTenant(page, {
      username: fixture.parent_username || "demo.parent",
    });

    const resultsUrl = `${tenantBase}/portal/parent/results/${fixture.student_id}/`;
    const htmlResp = await page.goto(resultsUrl, {
      waitUntil: "domcontentloaded",
      timeout: 120000,
    });
    expect(htmlResp?.status() ?? 500).toBeLessThan(400);
    const body = await page.locator("body").innerText();
    if (fixture.grade_label) {
      expect(body).toContain(fixture.grade_label);
    }
    if (fixture.subject_name) {
      expect(body).toContain(fixture.subject_name);
    }

    const pdfUrl = `${tenantBase}/reports/parent/report/${fixture.student_id}/`;
    const pdfResp = await page.request.get(pdfUrl);
    expect(pdfResp.status()).toBe(200);
    expect(pdfResp.headers()["content-type"] || "").toContain("pdf");
    const pdfBytes = await pdfResp.body();
    expect(pdfBytes.slice(0, 4).toString()).toBe("%PDF");

    const verifyUrl = `${tenantBase}/reports/verify-hash/?hash=${encodeURIComponent(
      fixture.sha256_hash
    )}`;
    const verifyResp = await page.request.get(verifyUrl);
    expect(verifyResp.status()).toBe(200);
    const verifyJson = await verifyResp.json();
    expect(verifyJson.verified).toBeTruthy();
    expect(verifyJson.sha256).toBe(fixture.sha256_hash);
  });
});
