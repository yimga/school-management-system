#!/usr/bin/env node
/** Minimal static server for serverless offline IndexedDB Playwright (no Django). */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_DIR = path.join(__dirname, "..", "tests", "e2e", "fixtures");
const PORT = Number(process.env.OFFLINE_E2E_PORT || "8777");
const BOOT = "offline-indexeddb-boot.html";

const server = http.createServer((req, res) => {
  const rel = (req.url || "/").split("?")[0].replace(/^\//, "") || BOOT;
  const file = path.join(FIXTURE_DIR, path.basename(rel));
  if (!file.startsWith(FIXTURE_DIR)) {
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
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(data);
  });
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`offline-e2e-fixture http://127.0.0.1:${PORT}/${BOOT}\n`);
});
