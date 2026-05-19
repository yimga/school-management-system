/**
 * Manifest <-> package.json version alignment guard.
 *
 * Catches the most common shipping mistake at edit time: bumping
 * `package.json` and forgetting to bump `manifest.json` (or vice
 * versa), which would otherwise fail in the release workflow only
 * AFTER the tag has been pushed.
 *
 * Also checks `manifest.firefox.json` when present.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const rootDir = resolve(__dirname, "..");

function readJson(name: string): Record<string, unknown> {
  const p = resolve(rootDir, name);
  return JSON.parse(readFileSync(p, "utf8")) as Record<string, unknown>;
}

describe("companion-extension version alignment", () => {
  const pkg = readJson("package.json");
  const manifest = readJson("manifest.json");

  it("package.json has a non-empty semver-shaped version", () => {
    const v = pkg.version;
    expect(typeof v).toBe("string");
    expect(v as string).toMatch(/^\d+\.\d+\.\d+(?:[-+][\w.-]+)?$/);
  });

  it("manifest.json version === package.json version", () => {
    expect(manifest.version).toBe(pkg.version);
  });

  it("manifest.json declares manifest_version 3", () => {
    expect(manifest.manifest_version).toBe(3);
  });

  it("manifest.firefox.json (if present) shares the same version", () => {
    const ffPath = resolve(rootDir, "manifest.firefox.json");
    if (!existsSync(ffPath)) {
      // optional — Chrome-only checkouts still pass
      return;
    }
    const ff = readJson("manifest.firefox.json");
    expect(ff.version).toBe(pkg.version);
    expect(ff.manifest_version).toBe(3);
    // Firefox MV3 requires the gecko id to be present.
    const settings = ff.browser_specific_settings as
      | { gecko?: { id?: string; strict_min_version?: string } }
      | undefined;
    expect(settings?.gecko?.id).toBeTruthy();
    expect(settings?.gecko?.strict_min_version).toBeTruthy();
  });
});
