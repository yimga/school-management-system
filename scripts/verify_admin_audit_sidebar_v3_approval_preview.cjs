#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const artifact = path.resolve(
  process.argv[2] || path.join(root, "var", "design-previews", "admin-audit-automation-and-tenant-sidebar-v3-before-after-approval-2026-08-27.html")
);
const output = path.resolve(
  process.argv[3] || path.join(root, "var", "design-previews", "admin-audit-automation-and-tenant-sidebar-v3-browser-proof-2026-08-27.json")
);
const screenshot = path.join(root, "var", "design-previews", "screenshots", "admin-audit-sidebar-v3-after-1440.png");

if (!fs.existsSync(artifact)) throw new Error(`Approval artifact not found: ${artifact}`);
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.mkdirSync(path.dirname(screenshot), { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const viewports = [
    { width: 1440, height: 1000 },
    { width: 1024, height: 900 },
    { width: 768, height: 900 },
    { width: 390, height: 844 },
  ];
  const proof = {
    schema: "rmc.admin-audit-sidebar-v3.1-approval-browser-proof.v1",
    artifact,
    generated_at: new Date().toISOString(),
    pass: true,
    results: [],
  };

  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(pathToFileURL(artifact).href, { waitUntil: "load" });

    const tabResults = [];
    for (const tab of ["findings", "preview", "proof", "contract"]) {
      await page.locator(`[data-tab="${tab}"]`).click();
      tabResults.push({ tab, visible: await page.locator(`#panel-${tab}`).isVisible() });
    }

    await page.locator('[data-tab="preview"]').click();
    await page.locator('[data-comparison="after"]').click();
    if (viewport.width <= 760) await page.locator('[data-device="mobile"]').click();
    await page.locator("#afterSearch").fill("academic");
    const searchStatus = await page.locator("#searchStatus").textContent();
    await page.locator("#afterSearch").click();
    const paletteOpened = await page.locator("#commandPalette").isVisible();
    await page.keyboard.press("Escape");
    const paletteClosed = !(await page.locator("#commandPalette").isVisible());
    const firstPinBefore = await page.locator("#pinList .nav-item").first().textContent();
    await page.locator("#reorderPins").click();
    const firstPinAfter = await page.locator("#pinList .nav-item").first().textContent();
    await page.locator('[data-scope="operator"]').click();
    const operatorWorkspace = (await page.locator("#workspaceName").textContent()) === "RunMyCampus Platform";
    const operatorIndexCtas = await page.locator("#operatorIndexCtas").isVisible();
    const operatorArea = await page.locator("#areaOne").textContent();
    await page.locator('[data-archetype="list"]').click();
    const operatorList = await page.locator("#archetype-list").isVisible() && (await page.locator("#listHeading").textContent()) === "Schools";
    await page.locator('[data-archetype="add"]').click();
    const operatorAdd = await page.locator("#archetype-add").isVisible() && (await page.locator("#addFieldTwoValue").textContent()).includes("runmycampus.com");
    await page.locator('[data-archetype="history"]').click();
    const operatorHistory = await page.locator("#archetype-history").isVisible();
    await page.locator('[data-scope="tenant"]').click();
    const tenantIsolated = (await page.locator("#workspaceName").textContent()) === "Gilead Technical High School" && (await page.locator("#areaOne").textContent()) === "Academic management" && !(await page.locator("#operatorIndexCtas").isVisible());
    await page.locator('[data-archetype="add"]').click();
    await page.locator("#focusToggle").click();
    const focusApplied = await page.locator("#afterFrame").evaluate(element => element.classList.contains("focus-mode"));
    const ambientHidden = !(await page.locator("#nowSection").isVisible());
    await page.locator("#focusToggle").click();
    await page.locator("#whyToggle").click();
    const explanationVisible = await page.locator("#whyPanel").isVisible();
    await page.locator('[data-tab="proof"]').click();
    await page.locator("#replayProof").click();
    await page.waitForFunction(() => document.querySelectorAll(".replay-state.pass").length === 4);
    const replayPassed = (await page.locator(".replay-state.pass").count()) === 4;
    await page.locator('[data-tab="preview"]').click();
    await page.locator("#themeToggle").click();
    const theme = await page.locator("html").getAttribute("data-theme");
    await page.locator("#themeToggle").click();
    await page.locator('[data-device="compact"]').click();
    const compactApplied = await page.locator("#afterFrame").evaluate(element => element.classList.contains("compact"));
    await page.locator('[data-device="mobile"]').click();
    const mobileApplied = await page.locator("#afterFrame").evaluate(element => element.classList.contains("mobile"));
    const geometry = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      h1: document.querySelectorAll("h1").length,
      stylesheetsInBody: document.body.querySelectorAll('link[rel="stylesheet"]').length,
    }));

    const result = {
      viewport,
      tabResults,
      searchStatus,
      paletteOpened,
      paletteClosed,
      reorderWorked: firstPinBefore !== firstPinAfter,
      operatorWorkspace,
      operatorIndexCtas,
      operatorArea,
      operatorList,
      operatorAdd,
      operatorHistory,
      tenantIsolated,
      focusApplied,
      ambientHidden,
      explanationVisible,
      replayPassed,
      theme,
      compactApplied,
      mobileApplied,
      geometry,
      consoleErrors: errors,
      pass:
        tabResults.every(item => item.visible) &&
        /matching destinations/.test(searchStatus || "") &&
        paletteOpened &&
        paletteClosed &&
        firstPinBefore !== firstPinAfter &&
        operatorWorkspace &&
        operatorIndexCtas &&
        operatorArea === "Schools & fleet" &&
        operatorList &&
        operatorAdd &&
        operatorHistory &&
        tenantIsolated &&
        focusApplied &&
        ambientHidden &&
        explanationVisible &&
        replayPassed &&
        theme === "light" &&
        compactApplied &&
        mobileApplied &&
        geometry.h1 === 1 &&
        geometry.stylesheetsInBody === 0 &&
        !geometry.overflow &&
        errors.length === 0,
    };
    proof.results.push(result);
    proof.pass = proof.pass && result.pass;

    if (viewport.width === 1440) {
      await page.locator('[data-device="desktop"]').click();
      await page.locator("#afterSearch").fill("");
      await page.locator("#toast").evaluate(element => { element.classList.remove("show"); element.style.display = "none"; });
      await page.screenshot({ path: screenshot, fullPage: true });
    }
    await page.close();
  }

  await browser.close();
  fs.writeFileSync(output, JSON.stringify(proof, null, 2) + "\n", "utf8");
  console.log(`ADMIN AUDIT + SIDEBAR V3 APPROVAL PREVIEW: ${proof.pass ? "PASS" : "FAIL"}`);
  proof.results.forEach(result => {
    console.log(`${result.viewport.width}x${result.viewport.height} pass=${result.pass} overflow=${result.geometry.overflow} errors=${result.consoleErrors.length}`);
  });
  console.log(`proof=${output}`);
  console.log(`screenshot=${screenshot}`);
  process.exitCode = proof.pass ? 0 : 1;
})().catch(error => {
  console.error(error);
  process.exit(1);
});
