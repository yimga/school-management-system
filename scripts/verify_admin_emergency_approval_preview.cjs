#!/usr/bin/env node
/* Browser proof for the self-contained admin emergency approval artifact. */

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (error) {
    const fallback = process.env.RMC_NODE_MODULES;
    if (!fallback) throw error;
    return require(path.join(fallback, "playwright"));
  }
}

const { chromium } = loadPlaywright();
const root = path.resolve(__dirname, "..");
const artifact = path.resolve(
  process.argv[2] || path.join(root, "var", "design-previews", "admin-emergency-full-canvas-and-provisioning-before-after-approval-2026-08-09.html")
);
const output = path.resolve(process.argv[3] || path.join(root, "var", "admin-emergency-approval-browser-proof-2026-08-09.json"));
const screenshotDir = path.join(root, "var", "design-previews", "screenshots");
const proofStem = path.basename(output, path.extname(output)).replace(/[^a-z0-9-]+/gi, "-").toLowerCase();

if (!fs.existsSync(artifact)) throw new Error(`Artifact does not exist: ${artifact}`);
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.mkdirSync(screenshotDir, { recursive: true });

function rgbChannels(value) {
  const match = value.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
  return match ? match.slice(1).map(Number) : [0, 0, 0];
}

function luminance(channels) {
  return channels.map(value => {
    const normalized = value / 255;
    return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
  }).reduce((total, value, index) => total + value * [0.2126, 0.7152, 0.0722][index], 0);
}

(async () => {
  const launchOptions = { headless: true };
  if (process.env.RMC_BROWSER_CHANNEL) launchOptions.channel = process.env.RMC_BROWSER_CHANNEL;
  const browser = await chromium.launch(launchOptions);
  const viewports = [
    { width: 1440, height: 1000 },
    { width: 1024, height: 900 },
    { width: 768, height: 900 },
    { width: 390, height: 844 },
  ];
  const proof = {
    schema: "rmc.admin-emergency-approval-browser-proof.v1",
    artifact,
    generated_at: new Date().toISOString(),
    pass: true,
    results: [],
  };

  for (const viewport of viewports) {
    console.log(`checking ${viewport.width}x${viewport.height}`);
    const page = await browser.newPage({ viewport });
    page.setDefaultTimeout(8000);
    page.setDefaultNavigationTimeout(12000);
    const errors = [];
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(pathToFileURL(artifact).href, { waitUntil: "load" });
    await page.waitForFunction(() => window.__RMC_PREVIEW_READY__ === true);

    const tabs = ["audit", "site", "coverage", "signup"];
    const tabResults = [];
    for (const tab of tabs) {
      await page.locator(`.tabs [data-view="${tab}"]`).click();
      tabResults.push({
        tab,
        visible: await page.locator(`#view-${tab}`).isVisible(),
        h1: await page.locator("h1:visible").count(),
      });
    }

    await page.locator('.tabs [data-view="signup"]').click();
    await page.locator('input[name="scope"][value="network"]').check();
    await page.locator('input[name="profile"][value="boarding"]').check();
    await page.locator('input[name="connectivity"][value="offline"]').check();
    await page.locator('input[name="size"][value="large"]').check();
    const recommendation = await page.locator("#rec-plan").textContent();
    const recommendationItems = await page.locator("#rec-list li").count();
    const themeToggle = page.locator("#theme-toggle");
    if (await themeToggle.isVisible()) await themeToggle.click();
    else await themeToggle.evaluate(element => element.click());
    const themeToggleWorked = (await themeToggle.textContent()).includes("Dark");
    if (await themeToggle.isVisible()) await themeToggle.click();
    else await themeToggle.evaluate(element => element.click());

    await page.locator('.tabs [data-view="site"]').click();
    await page.locator('[data-mode="before"]').click();
    const beforeBackground = await page.locator(".bad-guidance").evaluate(element => getComputedStyle(element).backgroundColor);
    await page.locator('[data-mode="after"]').click();
    const afterBackground = await page.locator(".guidance").evaluate(element => getComputedStyle(element).backgroundColor);
    const gridColumns = await page.locator("#mode-after .mini-workspace").evaluate(element => getComputedStyle(element).gridTemplateColumns);
    const geometry = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    }));

    const beforeLum = luminance(rgbChannels(beforeBackground));
    const afterLum = luminance(rgbChannels(afterBackground));
    const result = {
      viewport,
      tabs: tabResults,
      geometry,
      gridColumns,
      beforeBackground,
      afterBackground,
      beforeLuminance: beforeLum,
      afterLuminance: afterLum,
      consoleErrors: errors,
      recommendation,
      recommendationItems,
      themeToggleWorked,
      pass:
        !geometry.overflow &&
        errors.length === 0 &&
        tabResults.every(item => item.visible && item.h1 === 1) &&
        recommendation.trim() === "Campus Enterprise" &&
        recommendationItems >= 6 &&
        themeToggleWorked &&
        beforeLum > 0.9 &&
        afterLum < 0.08 &&
        (viewport.width <= 1024 ? gridColumns.split(" ").length === 1 : gridColumns.split(" ").length === 3),
    };
    proof.results.push(result);
    proof.pass = proof.pass && result.pass;

    if (viewport.width === 1440) {
      await page.screenshot({ path: path.join(screenshotDir, `${proofStem}-after-1440.png`), fullPage: true });
      await page.locator('[data-mode="before"]').click();
      await page.screenshot({ path: path.join(screenshotDir, `${proofStem}-before-1440.png`), fullPage: true });
    }
    await page.close();
    console.log(`checked ${viewport.width}x${viewport.height} pass=${result.pass}`);
  }

  await browser.close();
  fs.writeFileSync(output, JSON.stringify(proof, null, 2) + "\n", "utf8");
  console.log(`ADMIN EMERGENCY APPROVAL BROWSER PROOF: ${proof.pass ? "PASS" : "FAIL"}`);
  for (const result of proof.results) {
    console.log(`${result.viewport.width}x${result.viewport.height} pass=${result.pass} overflow=${result.geometry.overflow} grid=${result.gridColumns} errors=${result.consoleErrors.length}`);
  }
  console.log(`proof=${output}`);
  process.exitCode = proof.pass ? 0 : 1;
})().catch(error => {
  console.error(error);
  process.exit(1);
});
