#!/usr/bin/env node
/** Static server for globe preview Playwright (repo root on :8765). */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PORT = Number(process.env.GLOBE_PREVIEW_PORT || 8765);
const HOST = process.env.GLOBE_PREVIEW_HOST || '127.0.0.1';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
};

http
  .createServer((req, res) => {
    const raw = (req.url || '/').split('?')[0];
    let rel = decodeURIComponent(raw.replace(/^\//, ''));
    if (!rel || raw.endsWith('/')) {
      rel = path.join(rel, 'index.html');
    }
    const file = path.normalize(path.join(ROOT, rel));
    if (!file.startsWith(ROOT)) {
      res.writeHead(403);
      res.end('Forbidden');
      return;
    }
    fs.readFile(file, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end('Not found');
        return;
      }
      const ext = path.extname(file).toLowerCase();
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
      res.end(data);
    });
  })
  .listen(PORT, HOST, () => {
    process.stdout.write(`GLOBE_PREVIEW_STATIC_READY http://${HOST}:${PORT}\n`);
  });
