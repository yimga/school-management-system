#!/usr/bin/env node
/* Real-browser smoke for self-hosted Tesseract.js assets. */

import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { chromium } from "playwright";

const root = path.resolve(import.meta.dirname, "..");
const evidencePath = path.join(
  root,
  "var",
  "evidence",
  "ocr",
  "browser_tesseract_smoke.json",
);
const contentTypes = {
  ".js": "text/javascript; charset=utf-8",
  ".gz": "application/gzip",
  ".json": "application/json",
};

const smokeHtml = `<!doctype html>
<html><body>
<canvas id="sample" width="1200" height="220"></canvas>
<script src="/static/js/vendor/tesseract/tesseract.min.js"></script>
<script>
window.__ocrResult = {done: false};
(async function () {
  const canvas = document.getElementById("sample");
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#000";
  ctx.font = "bold 64px Arial";
  ctx.fillText("STD001 12 13 14", 40, 130);
  let worker;
  try {
    worker = await Tesseract.createWorker("eng", 1, {
      workerPath: "/static/js/vendor/tesseract/worker.min.js",
      corePath: "/static/js/vendor/tesseract/",
      langPath: "/static/js/vendor/tesseract/"
    });
    const result = await worker.recognize(canvas, {}, {text: true, blocks: true});
    window.__ocrResult = {
      done: true,
      ok: true,
      text: result.data.text || "",
      confidence: result.data.confidence || 0,
      has_blocks: Array.isArray(result.data.blocks)
    };
  } catch (error) {
    window.__ocrResult = {done: true, ok: false, error: String(error)};
  } finally {
    if (worker) await worker.terminate();
  }
})();
</script>
</body></html>`;

function safeFilePath(urlPath) {
  const relative = decodeURIComponent(urlPath).replace(/^\/+/, "");
  const candidate = path.resolve(root, relative);
  return candidate.startsWith(root + path.sep) ? candidate : null;
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url || "/", "http://127.0.0.1");
  if (url.pathname === "/") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(smokeHtml);
    return;
  }
  const filePath = safeFilePath(url.pathname);
  if (!filePath || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    response.writeHead(404);
    response.end("not found");
    return;
  }
  response.writeHead(200, {
    "Content-Type":
      contentTypes[path.extname(filePath).toLowerCase()] ||
      "application/octet-stream",
    "Cache-Control": "no-store",
  });
  fs.createReadStream(filePath).pipe(response);
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const origin = `http://127.0.0.1:${address.port}`;
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.route("**/*", async (route) => {
    const requestUrl = new URL(route.request().url());
    if (requestUrl.origin !== origin) {
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  await page.goto(origin, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__ocrResult?.done, null, {
    timeout: 120000,
  });
  const result = await page.evaluate(() => window.__ocrResult);
  const normalized = String(result.text || "").replace(/\s+/g, " ").trim();
  const passed =
    result.ok === true &&
    /STD[O0]{2}1/i.test(normalized) &&
    normalized.includes("12") &&
    normalized.includes("13") &&
    normalized.includes("14");
  const evidence = {
    schema_version: 1,
    passed,
    localhost_only: true,
    runtime: "tesseract.js@7.0.0",
    recognized_text: normalized,
    confidence: result.confidence || 0,
    has_blocks: result.has_blocks === true,
    error: result.error || "",
  };
  fs.mkdirSync(path.dirname(evidencePath), { recursive: true });
  fs.writeFileSync(evidencePath, JSON.stringify(evidence, null, 2) + "\n");
  if (!passed) {
    console.error("TESSERACT_BROWSER_SMOKE_FAIL", evidence);
    process.exitCode = 1;
  } else {
    console.log(
      `TESSERACT_BROWSER_SMOKE_PASS confidence=${evidence.confidence} text=${JSON.stringify(normalized)}`,
    );
  }
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
