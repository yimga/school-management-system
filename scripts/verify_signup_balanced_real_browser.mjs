#!/usr/bin/env node
/** Validate the actual public signup surface at the approval breakpoints/themes. */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LOCK = JSON.parse(fs.readFileSync(path.join(ROOT, "var", "admin-approval-build-lock.json"), "utf8"));
const port = Number(process.env.VISUAL_QA_PORT || 8020);
const host = (process.env.RMC_PUBLIC_HOST || "runmycampus.com").trim();
const output = path.join(ROOT, "artifacts", "django-admin-canvas-live", "signup-balanced-v3-real-browser.json");
const userAgent =
  process.env.VISUAL_QA_USER_AGENT ||
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const isExpectedLocalHttpConsoleNoise = (message) =>
  /Cross-Origin-Opener-Policy header has been ignored.*origin was untrustworthy/i.test(message);
const cases = [
  [1440, 900],
  [1024, 768],
  [768, 900],
  [390, 844],
].flatMap(([width, height]) => ["light", "dark"].map((theme) => ({ width, height, theme })));

const browser = await chromium.launch({
  headless: true,
  args: [`--host-resolver-rules=MAP ${host} 127.0.0.1`],
});
const results = [];
for (const item of cases) {
  const context = await browser.newContext({
    viewport: { width: item.width, height: item.height },
    colorScheme: item.theme,
    userAgent,
    serviceWorkers: "block",
  });
  await context.addInitScript((theme) => {
    localStorage.setItem("runmycampus-theme-preference", theme);
  }, item.theme);
  const page = await context.newPage();
  const failedResources = [];
  const consoleErrors = [];
  page.on("requestfailed", (request) => failedResources.push(`${request.resourceType()}:${request.url()}`));
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      !/favicon/i.test(message.text()) &&
      !isExpectedLocalHttpConsoleNoise(message.text())
    ) consoleErrors.push(message.text());
  });
  const response = await page.goto(`http://${host}:${port}/signup/`, {
    waitUntil: "domcontentloaded",
    timeout: 120_000,
  });
  await page.waitForTimeout(500);
  await page.locator(".rmc-signup-fine-tune > summary").click();
  await page.locator('[name="campus_count"]').fill("4");
  await page.locator('[name="staff_count"]').fill("300");
  await page.waitForTimeout(100);
  const dom = await page.evaluate(({ expectedTheme, width }) => {
    const form = document.querySelector('[data-rmc-signup-form="1"]');
    const card = document.querySelector('[data-rmc-signup-balanced="v3"]');
    const grid = form ? getComputedStyle(form).gridTemplateColumns : "";
    const tracks = (grid.match(/-?\d+(?:\.\d+)?px/g) || []).length;
    const rect = card?.getBoundingClientRect();
    const bodyLinks = document.querySelectorAll('body link[rel~="stylesheet"]').length;
    return {
      h1: [...document.querySelectorAll("h1")].filter((node) => {
        const box = node.getBoundingClientRect();
        return box.width > 0 && box.height > 0;
      }).length,
      pageOverflow: Math.max(0, document.documentElement.scrollWidth - width),
      bodyLinks,
      tracks,
      cardWidthRatio: rect ? rect.width / width : 0,
      balanced: Boolean(card && form),
      optionalInputs: [
        "campus_count",
        "staff_count",
        "operating_model",
        "connectivity_profile",
        "payment_profile",
        "go_live_timeline",
      ].every((name) => document.querySelector(`[name="${name}"]`)),
      recommendationOnly: /recommendation only/i.test(document.body.innerText),
      plan: document.querySelector("[data-rmc-recommendation-plan]")?.textContent?.trim() || "",
      theme: document.documentElement.dataset.theme || document.documentElement.dataset.bsTheme || expectedTheme,
    };
  }, { expectedTheme: item.theme, width: item.width });
  const findings = [];
  if (response?.status() !== 200) findings.push(`http:${response?.status() || 0}`);
  if (dom.h1 !== 1) findings.push(`h1:${dom.h1}`);
  if (dom.pageOverflow > 1) findings.push(`overflow:${dom.pageOverflow}`);
  if (dom.bodyLinks) findings.push(`body-stylesheets:${dom.bodyLinks}`);
  if (!dom.balanced || !dom.optionalInputs) findings.push("balanced-contract-missing");
  if (item.width <= 1024 ? dom.tracks !== 1 : dom.tracks !== 12) findings.push(`grid-tracks:${dom.tracks}`);
  if (dom.cardWidthRatio < (item.width <= 390 ? 0.92 : 0.72)) findings.push(`card-width:${dom.cardWidthRatio}`);
  if (!dom.recommendationOnly) findings.push("recommendation-disclaimer-missing");
  if (!/campus enterprise/i.test(dom.plan)) findings.push(`live-plan:${dom.plan}`);
  if (failedResources.length) findings.push(`failed-resources:${failedResources.join(",")}`);
  if (consoleErrors.length) findings.push(`console:${consoleErrors.join("|")}`);
  results.push({ ...item, pass: !findings.length, findings, dom, failedResources, consoleErrors });
  console.log(`${findings.length ? "FAIL" : "PASS"} signup ${item.width} ${item.theme}`);
  await context.close();
}
const supportingPages = [
  { name: "guided-onboarding", path: "/onboard/?step=1" },
  // A verification URL without its one-time token is intentionally invalid,
  // but it must still render the balanced, actionable error checkpoint.
  { name: "verification", path: "/verify-signup/", expectedStatus: 400 },
  { name: "verification-resend", path: "/verify-signup/resend/" },
];
for (const item of [
  { width: 1440, height: 900, theme: "light" },
  { width: 390, height: 844, theme: "dark" },
]) {
  for (const supporting of supportingPages) {
    const context = await browser.newContext({
      viewport: { width: item.width, height: item.height },
      colorScheme: item.theme,
      userAgent,
      serviceWorkers: "block",
    });
    await context.addInitScript((theme) => {
      localStorage.setItem("runmycampus-theme-preference", theme);
    }, item.theme);
    const page = await context.newPage();
    const failedResources = [];
    const consoleErrors = [];
    page.on("requestfailed", (request) => failedResources.push(`${request.resourceType()}:${request.url()}`));
    page.on("console", (message) => {
      if (
        message.type() === "error" &&
        !/favicon/i.test(message.text()) &&
        !isExpectedLocalHttpConsoleNoise(message.text())
      ) consoleErrors.push(message.text());
    });
    const response = await page.goto(`http://${host}:${port}${supporting.path}`, {
      waitUntil: "domcontentloaded",
      timeout: 120_000,
    });
    await page.waitForTimeout(350);
    const dom = await page.evaluate(({ width }) => {
      const visible = (node) => {
        const box = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return box.width > 0 && box.height > 0 && style.display !== "none" && style.visibility !== "hidden";
      };
      const balancedStyles = [...document.querySelectorAll('head link[rel~="stylesheet"]')]
        .filter((link) => /rmc-signup-balanced-v3\.css/.test(link.href));
      const main = document.querySelector('[data-shell-page="onboarding-wizard"], .rmc-security-checkpoint-page, .auth-shell');
      const rect = main?.getBoundingClientRect();
      return {
        h1: [...document.querySelectorAll("h1")].filter(visible).length,
        pageOverflow: Math.max(0, document.documentElement.scrollWidth - width),
        bodyLinks: document.querySelectorAll('body link[rel~="stylesheet"]').length,
        balancedStyles: balancedStyles.length,
        shellWidthRatio: rect ? rect.width / width : 0,
        template: document.documentElement.dataset.rmcIsomorphicTemplate || "",
      };
    }, { width: item.width });
    const findings = [];
    const expectedStatus = supporting.expectedStatus || 200;
    const actionableConsoleErrors = consoleErrors.filter((message) =>
      !(expectedStatus === 400 && /Failed to load resource: the server responded with a status of 400/i.test(message))
    );
    if (response?.status() !== expectedStatus) findings.push(`http:${response?.status() || 0}`);
    if (dom.h1 !== 1) findings.push(`h1:${dom.h1}`);
    if (dom.pageOverflow > 1) findings.push(`overflow:${dom.pageOverflow}`);
    if (dom.bodyLinks) findings.push(`body-stylesheets:${dom.bodyLinks}`);
    if (dom.balancedStyles !== 1) findings.push(`balanced-styles:${dom.balancedStyles}`);
    if (dom.template !== "onboarding-wizard") findings.push(`template:${dom.template}`);
    if (dom.shellWidthRatio < (item.width <= 390 ? 0.9 : 0.45)) findings.push(`shell-width:${dom.shellWidthRatio}`);
    if (failedResources.length) findings.push(`failed-resources:${failedResources.join(",")}`);
    if (actionableConsoleErrors.length) findings.push(`console:${actionableConsoleErrors.join("|")}`);
    results.push({
      ...item,
      page: supporting.name,
      path: supporting.path,
      pass: !findings.length,
      findings,
      dom,
      failedResources,
      consoleErrors,
      actionableConsoleErrors,
    });
    console.log(`${findings.length ? "FAIL" : "PASS"} ${supporting.name} ${item.width} ${item.theme}`);
    await context.close();
  }
}
await browser.close();
const report = {
  generatedAt: new Date().toISOString(),
  build: LOCK.build_id,
  cacheBust: LOCK.cache_bust,
  serviceWorker: LOCK.sw_version,
  pass: results.every((item) => item.pass),
  results,
};
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
if (!report.pass) {
  console.error(`SIGNUP_BALANCED_REAL_BROWSER_FAIL ${path.relative(ROOT, output)}`);
  process.exitCode = 1;
} else {
  console.log(`SIGNUP_BALANCED_REAL_BROWSER_PASS ${path.relative(ROOT, output)}`);
}
