// Stability-contract tests for the 1.0.0-rc.1 release candidate (v3.38.0).
//
// Six tests, mirroring the Python stability suite:
//  1. STABILITY.md "Public API surface" names are all actually exported.
//  2. package.json `version` matches the exported `VERSION` constant.
//  3. CHANGELOG.md exists, parses, and lists a `1.0.0-rc.1` release.
//  4. STABILITY.md mentions `acceptLegacy`.
//  5. Deprecated alias `verifySignature` still works and carries a
//     `@deprecated` JSDoc tag in its source.
//  6. MIGRATION_TO_1_0.md exists.

import { describe, expect, it } from "vitest";
import { readFileSync, existsSync, statSync } from "node:fs";
import { resolve } from "node:path";

import * as pkg from "../src/index";
import { computeSignature, verifySignature } from "../src/verifier";

const PKG_ROOT = resolve(__dirname, "..");
const PACKAGE_JSON = resolve(PKG_ROOT, "package.json");
const CHANGELOG = resolve(PKG_ROOT, "CHANGELOG.md");
const STABILITY = resolve(PKG_ROOT, "STABILITY.md");
const MIGRATION = resolve(PKG_ROOT, "MIGRATION_TO_1_0.md");
const VERIFIER_SRC = resolve(PKG_ROOT, "src/verifier.ts");

const EXPECTED_RC_VERSION = "1.0.0-rc.1";

describe("1.0.0-rc.1 stability contract", () => {
  it("(1) STABILITY.md public-API surface names are all exported", () => {
    const stab = readFileSync(STABILITY, "utf-8");
    // Grab the section between "## Public API surface" and the next "## "
    const sectionMatch = stab.match(
      /## Public API surface\s*([\s\S]*?)\n## /,
    );
    expect(sectionMatch).not.toBeNull();
    const section = (sectionMatch as RegExpMatchArray)[1];
    const docNames = new Set<string>();
    const re = /-\s+`([A-Za-z_][A-Za-z0-9_]*)`/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(section)) !== null) {
      docNames.add(m[1]);
    }
    expect(docNames.size).toBeGreaterThan(0);
    const exported = new Set(Object.keys(pkg));
    // Types are erased at runtime so they won't appear in `Object.keys`.
    // We restrict the assertion to value exports — pull the type names
    // out of the STABILITY doc by scanning the "Types" subsection.
    const typesSubMatch = stab.match(
      /\*\*Types[^*]*\*\*[^-]*([\s\S]*?)Anything not listed/,
    );
    const typeNames = new Set<string>();
    if (typesSubMatch) {
      const re2 = /-\s+`([A-Za-z_][A-Za-z0-9_]*)`/g;
      let mm: RegExpExecArray | null;
      while ((mm = re2.exec(typesSubMatch[1])) !== null) {
        typeNames.add(mm[1]);
      }
    }
    const expectedValueNames = [...docNames].filter((n) => !typeNames.has(n));
    const missing = expectedValueNames.filter((n) => !exported.has(n));
    expect(missing).toEqual([]);
  });

  it("(2) package.json version matches VERSION constant", () => {
    const pkgJson = JSON.parse(readFileSync(PACKAGE_JSON, "utf-8"));
    expect(pkgJson.version).toBe(EXPECTED_RC_VERSION);
    expect(pkg.VERSION).toBe(EXPECTED_RC_VERSION);
  });

  it("(3) CHANGELOG.md exists, parses, and lists 1.0.0-rc.1", () => {
    expect(existsSync(CHANGELOG)).toBe(true);
    const text = readFileSync(CHANGELOG, "utf-8");
    // ## [<version>] — <date>
    const re = /^##\s*\[([^\]]+)\]\s*[—-]\s*(\d{4}-\d{2}-\d{2})\s*$/gm;
    const versions = new Set<string>();
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      versions.add(m[1]);
    }
    expect(versions.size).toBeGreaterThanOrEqual(2);
    expect(versions.has(EXPECTED_RC_VERSION)).toBe(true);
  });

  it("(4) STABILITY.md mentions acceptLegacy", () => {
    const stab = readFileSync(STABILITY, "utf-8");
    expect(stab).toContain("acceptLegacy");
  });

  it("(5) deprecated alias verifySignature still works and carries @deprecated", async () => {
    const body = new TextEncoder().encode('{"hello":"world"}');
    const secret = new TextEncoder().encode("sk_test_secret");
    const sig = await computeSignature(body, secret);
    const ok = await verifySignature(body, sig, secret);
    expect(ok).toBe(true);

    // JSDoc `@deprecated` is the canonical mechanism in TypeScript;
    // assert it is present in the source for the symbol.
    const src = readFileSync(VERIFIER_SRC, "utf-8");
    // Find the JSDoc block immediately preceding the
    // `export async function verifySignature(` declaration.
    const idx = src.indexOf("export async function verifySignature(");
    expect(idx).toBeGreaterThan(0);
    const preceding = src.slice(Math.max(0, idx - 1000), idx);
    expect(preceding).toMatch(/@deprecated/);
  });

  it("(6) MIGRATION_TO_1_0.md exists", () => {
    expect(existsSync(MIGRATION)).toBe(true);
    expect(statSync(MIGRATION).size).toBeGreaterThan(200);
  });
});
