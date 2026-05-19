#!/usr/bin/env node
// Package the built extension into a publishable zip.
//
// Reads the version from package.json, walks the build output directory
// (`dist/` for Chrome/Edge or `dist-firefox/` for Firefox depending on
// MODE env var), and writes a single zip into `dist-zip/`.
//
// Implementation note: uses Node's built-in `zlib.deflateRawSync` and
// hand-written ZIP central-directory records so we don't add a runtime
// dependency. Stored entries use deflate compression for the small
// JS/HTML/JSON files; PNG icons are stored uncompressed (they don't
// compress meaningfully and storing them avoids any deflate edge case).
//
// Usage:
//   node scripts/package-extension.mjs            # Chrome/Edge from dist/
//   MODE=firefox node scripts/package-extension.mjs  # Firefox from dist-firefox/
import { readFileSync, writeFileSync, readdirSync, statSync, existsSync, mkdirSync } from "node:fs";
import { resolve, join, relative, sep } from "node:path";
import { deflateRawSync } from "node:zlib";
import { fileURLToPath } from "node:url";

// CRC32 (RFC 1952) — Node 20 has no native export, so we ship a small
// table-based implementation. Node 22 has zlib.crc32 we could swap to.
const CRC_TABLE = new Uint32Array(256);
for (let n = 0; n < 256; n++) {
  let c = n;
  for (let k = 0; k < 8; k++) {
    c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  }
  CRC_TABLE[n] = c >>> 0;
}
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

const __filename = fileURLToPath(import.meta.url);
const here = resolve(__filename, "..");
const rootDir = resolve(here, "..");
const mode = process.env.MODE === "firefox" ? "firefox" : "chrome";
const sourceDir = mode === "firefox" ? "dist-firefox" : "dist";
const sourcePath = resolve(rootDir, sourceDir);
if (!existsSync(sourcePath)) {
  console.error(`[package] missing build output dir: ${sourcePath}`);
  console.error(`[package] run \`pnpm run build${mode === "firefox" ? ":firefox" : ""}\` first`);
  process.exit(1);
}
const pkg = JSON.parse(readFileSync(resolve(rootDir, "package.json"), "utf8"));
const version = pkg.version;
const zipDir = resolve(rootDir, "dist-zip");
mkdirSync(zipDir, { recursive: true });
const outName =
  mode === "firefox"
    ? `companion-extension-firefox-${version}.zip`
    : `companion-extension-${version}.zip`;
const outPath = resolve(zipDir, outName);

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    const s = statSync(p);
    if (s.isDirectory()) {
      out.push(...walk(p));
    } else {
      out.push(p);
    }
  }
  return out;
}

// Minimal ZIP writer. Each file is appended as a local-file header +
// (optionally compressed) bytes, then a central-directory record. EOCD
// closes the file. CRC32 from zlib.
const files = walk(sourcePath);
const localChunks = [];
const centralChunks = [];
let offset = 0;

function writeUInt16(n) {
  const b = Buffer.alloc(2);
  b.writeUInt16LE(n, 0);
  return b;
}
function writeUInt32(n) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(n >>> 0, 0);
  return b;
}

for (const filePath of files) {
  const rel = relative(sourcePath, filePath).split(sep).join("/");
  const data = readFileSync(filePath);
  // Use deflate for text-y types; store for PNG/ZIP/binary.
  const lower = rel.toLowerCase();
  const isBinary = lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".zip");
  const method = isBinary ? 0 : 8;
  const compressed = method === 8 ? deflateRawSync(data) : data;
  const crc = crc32(data) >>> 0;
  const nameBuf = Buffer.from(rel, "utf8");
  const localHeader = Buffer.concat([
    writeUInt32(0x04034b50),
    writeUInt16(20),
    writeUInt16(0),
    writeUInt16(method),
    writeUInt16(0),
    writeUInt16(0),
    writeUInt32(crc),
    writeUInt32(compressed.length),
    writeUInt32(data.length),
    writeUInt16(nameBuf.length),
    writeUInt16(0),
    nameBuf,
  ]);
  localChunks.push(localHeader, compressed);
  const central = Buffer.concat([
    writeUInt32(0x02014b50),
    writeUInt16(20),
    writeUInt16(20),
    writeUInt16(0),
    writeUInt16(method),
    writeUInt16(0),
    writeUInt16(0),
    writeUInt32(crc),
    writeUInt32(compressed.length),
    writeUInt32(data.length),
    writeUInt16(nameBuf.length),
    writeUInt16(0),
    writeUInt16(0),
    writeUInt16(0),
    writeUInt16(0),
    writeUInt32(0),
    writeUInt32(offset),
    nameBuf,
  ]);
  centralChunks.push(central);
  offset += localHeader.length + compressed.length;
}

const centralBuf = Buffer.concat(centralChunks);
const eocd = Buffer.concat([
  writeUInt32(0x06054b50),
  writeUInt16(0),
  writeUInt16(0),
  writeUInt16(files.length),
  writeUInt16(files.length),
  writeUInt32(centralBuf.length),
  writeUInt32(offset),
  writeUInt16(0),
]);
const zipBuf = Buffer.concat([...localChunks, centralBuf, eocd]);
writeFileSync(outPath, zipBuf);
console.log(`[package] wrote ${outPath} (${files.length} files, ${zipBuf.length} bytes)`);
