#!/usr/bin/env node
/** Minimal static server for serverless offline IndexedDB Playwright (no Django). */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_DIR = path.resolve(__dirname, "..", "tests", "e2e", "fixtures");
const PORT = Number(process.env.OFFLINE_E2E_PORT || "8777");
const HOST = process.env.OFFLINE_E2E_HOST || "127.0.0.1";
const BOOT = "offline-indexeddb-boot.html";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
};

function safeFixturePath(urlPath) {
  const rel = (urlPath || "/").split("?")[0].replace(/^\//, "") || BOOT;
  const file = path.resolve(FIXTURE_DIR, path.basename(rel));
  const rootWithSep = FIXTURE_DIR.endsWith(path.sep)
    ? FIXTURE_DIR
    : FIXTURE_DIR + path.sep;
  if (file !== FIXTURE_DIR && !file.startsWith(rootWithSep)) {
    return null;
  }
  return file;
}

const server = http.createServer((req, res) => {
  const file = safeFixturePath(req.url);
  if (!file) {
    res.writeHead(403);
    res.end("forbidden");
    return;
  }
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    const ext = path.extname(file).toLowerCase();
    res.writeHead(200, {
      "Content-Type": MIME[ext] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    res.end(data);
  });
});

server.on("error", (err) => {
  process.stderr.write(
    `offline-e2e-fixture listen error on ${HOST}:${PORT}: ${err.message}\n`,
  );
  process.exit(1);
});

server.listen(PORT, HOST, () => {
  process.stdout.write(
    `offline-e2e-fixture http://${HOST}:${PORT}/${BOOT}\n`,
  );
});
