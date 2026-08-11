#!/usr/bin/env node
/**
 * Real-host browser proof for the tenant experience-template runtime bridge.
 *
 * This intentionally maps the production-shaped tenant hostname to a local
 * Django server.  It requires an authenticated tenant session exported by
 * scripts/export_django_admin_real_host_sessions.py.
 */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LOCK = JSON.parse(
  fs.readFileSync(path.join(ROOT, "var", "admin-approval-build-lock.json"), "utf8"),
);
const tenantHost = (process.env.RMC_ADMIN_TENANT_HOST || "gilead-tech.runmycampus.com").trim();
const port = Number(process.env.RMC_BROWSER_PORT || "8031");
const sessionId = (process.env.RMC_ADMIN_TENANT_SESSIONID || "").trim();
const deviceTrustToken = (process.env.RMC_MFA_DEVICE_TRUST_TOKEN || "").trim();
const templateKey = (process.env.RMC_EXPERIENCE_TEMPLATE_KEY || "admin-school-command-center").trim();
const base = `http://${tenantHost}:${port}`;
const artifactPath = path.join(ROOT, "artifacts", "tenant-experience-runtime-browser.json");
const userAgent =
  process.env.VISUAL_QA_USER_AGENT ||
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

if (!sessionId) {
  throw new Error("RMC_ADMIN_TENANT_SESSIONID is required");
}

const browser = await chromium.launch({
  headless: true,
  args: [`--host-resolver-rules=MAP ${tenantHost} 127.0.0.1`],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  colorScheme: "dark",
  userAgent,
});
await context.addCookies([
  {
    name: "sessionid",
    value: sessionId,
    domain: tenantHost,
    path: "/",
    httpOnly: true,
    sameSite: "Lax",
    secure: false,
  },
]);
if (deviceTrustToken) {
  await context.addCookies([
    {
      name: "mfa_device_trust",
      value: deviceTrustToken,
      domain: tenantHost,
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
      secure: false,
    },
  ]);
}

const page = await context.newPage();
const checks = [];
const record = (name, pass, evidence = "") => checks.push({ name, pass: Boolean(pass), evidence });

try {
  const launchResponse = await page.goto(`${base}/studio/launch/`, {
    waitUntil: "domcontentloaded",
    timeout: 120_000,
  });
  record("studio launch returns HTTP 200", launchResponse?.status() === 200, launchResponse?.status());
  record("studio launch keeps tenant hostname", new URL(page.url()).hostname === tenantHost, page.url());
  record(
    "studio launch remains authenticated",
    !new URL(page.url()).pathname.startsWith("/authentication/"),
    page.url(),
  );

  const experienceStep = page.locator("li", { hasText: "Choose experience template" }).first();
  const experienceStepPresent = (await experienceStep.count()) === 1;
  record("experience checklist step is present", experienceStepPresent);
  record(
    "applied experience checklist step is green",
    experienceStepPresent &&
      (await experienceStep.locator(".text-success, .bi-check-circle-fill").count()) > 0,
    experienceStepPresent ? (await experienceStep.textContent())?.trim() || "" : "step missing",
  );

  const runtimeTemplate = await page
    .locator("[data-rmc-experience-template]")
    .first()
    .getAttribute("data-rmc-experience-template");
  record("active template reaches runtime shell", runtimeTemplate === templateKey, runtimeTemplate || "missing");

  const previewResponse = await page.goto(
    `${base}/school/studio/templates/${encodeURIComponent(templateKey)}/preview/`,
    { waitUntil: "domcontentloaded", timeout: 120_000 },
  );
  record("template preview returns HTTP 200", previewResponse?.status() === 200, previewResponse?.status());
  record("preview has one visible H1", (await page.locator("h1:visible").count()) === 1);

  const iframe = page.locator("iframe[data-rmc-preview-frame]").first();
  const iframeSrc = (await iframe.getAttribute("src")) || "";
  record("preview owns a genuine iframe target", iframeSrc.startsWith("/") && !iframeSrc.includes("/portal/preview"), iframeSrc);
  await iframe.scrollIntoViewIfNeeded();
  const iframeHandle = await iframe.elementHandle();
  const frame = iframeHandle ? await iframeHandle.contentFrame() : null;
  if (frame) {
    await frame.waitForLoadState("domcontentloaded", { timeout: 120_000 });
    record("preview iframe loads tenant content", !frame.url().startsWith("about:"), frame.url());
    record(
      "preview iframe preserves the admin preview target",
      new URL(frame.url()).pathname === "/authentication/backend/",
      frame.url(),
    );
    record("preview iframe is not a 404 surface", (await frame.getByText("Page not found", { exact: true }).count()) === 0, frame.url());
  } else {
    record("preview iframe loads tenant content", false, "content frame unavailable");
    record("preview iframe preserves the admin preview target", false, "content frame unavailable");
    record("preview iframe is not a 404 surface", false, "content frame unavailable");
  }

  const observedStatuses = [];
  const statusListener = (response) => {
    if (response.url().includes("/academics/timetable/generate/")) observedStatuses.push(response.status());
  };
  page.on("response", statusListener);
  await page.goto(`${base}/academics/timetable/generate/`, {
    waitUntil: "domcontentloaded",
    timeout: 120_000,
  });
  page.off("response", statusListener);
  record("timetable GET does not return 405", !observedStatuses.includes(405), observedStatuses.join(","));
  record(
    "timetable GET reaches canonical workspace",
    new URL(page.url()).pathname !== "/academics/timetable/generate/",
    page.url(),
  );
} catch (error) {
  record("browser journey completes", false, error?.stack || String(error));
} finally {
  await browser.close();
}

const payload = {
  generatedAt: new Date().toISOString(),
  build: LOCK.build_id,
  host: tenantHost,
  templateKey,
  pass: checks.every((check) => check.pass),
  checks,
};
fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
fs.writeFileSync(artifactPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

for (const check of checks) {
  console.log(`${check.pass ? "PASS" : "FAIL"} ${check.name}${check.evidence ? `: ${check.evidence}` : ""}`);
}
console.log(`report=${path.relative(ROOT, artifactPath)}`);
process.exit(payload.pass ? 0 : 1);
