import { chromium } from "playwright";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

try {
  const file = path.resolve(__dirname, "index.html");
  const url = "file:///" + file.replace(/\\/g, "/");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(400);
  await page.screenshot({
    path: path.join(__dirname, "compare-side-by-side.png"),
    fullPage: true,
  });
  await page.click('[data-tab="after"]');
  await page.waitForTimeout(200);
  await page.locator("#panel-after .after-stage").screenshot({
    path: path.join(__dirname, "after-chrome.png"),
  });
  await browser.close();
  console.log("SHOTS_OK", url);
} catch (e) {
  console.error("SHOTS_SKIP", e.message);
}
