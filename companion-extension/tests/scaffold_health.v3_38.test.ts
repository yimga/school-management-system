/**
 * v3.38.0 — Scaffold-health sanity tests.
 *
 * Locks the existence + shape of the toolchain scaffolding that the
 * existing `.ts` source files in `src/` depend on. A prior v3.37.0
 * agent report flagged the entire scaffolding (manifest.json,
 * vite.config.ts, package.json, tsconfig.json) was absent from the
 * worktree; this test exists so future tree-pruning never silently
 * removes the build files again.
 *
 *   1. package.json parses as JSON and exposes the expected scripts.
 *   2. manifest.json parses as JSON and is a valid MV3 shape.
 *   3. tsconfig.json parses (with comment-tolerance) and declares strict mode.
 *   4. vite.config.ts is present on disk.
 */
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const rootDir = resolve(__dirname, "..");

/** Strip /* … *\/ block comments + // line comments so we can JSON.parse
 *  tsconfig.json (which historically allows trailing-comma / comment
 *  JSON5-lite syntax). Our tsconfig.json ships strict-JSON today but we
 *  keep the helper so re-formatting with comments doesn't break the
 *  scaffold check. */
function parseTolerantJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    // Fall through to the comment-tolerant path for JSONC-like edits.
  }
  const stripped = text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/,(\s*[}\]])/g, "$1");
  return JSON.parse(stripped);
}

describe("companion-extension scaffold health (v3.38.0)", () => {
  it("package.json parses + declares build/dev/test/typecheck/lint scripts", () => {
    const path = resolve(rootDir, "package.json");
    expect(existsSync(path)).toBe(true);
    const pkg = JSON.parse(readFileSync(path, "utf8")) as {
      name: string;
      private?: boolean;
      scripts: Record<string, string>;
      devDependencies: Record<string, string>;
      dependencies?: Record<string, string>;
    };
    expect(pkg.name).toBe("@runmycampus/companion-extension");
    expect(pkg.private).toBe(true);
    for (const expected of ["build", "dev", "test", "typecheck", "lint"]) {
      expect(
        Object.prototype.hasOwnProperty.call(pkg.scripts, expected)
      ).toBe(true);
    }
    // Toolchain deps the existing .ts source files need.
    expect(pkg.devDependencies.vite).toBeDefined();
    expect(pkg.devDependencies.vitest).toBeDefined();
    expect(pkg.devDependencies.typescript).toBeDefined();
    expect(pkg.devDependencies["@types/chrome"]).toBeDefined();
    // Runtime dep needed by future sealed-box wiring.
    expect(pkg.dependencies?.["libsodium-wrappers"]).toBeDefined();
  });

  it("manifest.json parses + is valid Manifest V3 with 6 SIS host_permissions", () => {
    const path = resolve(rootDir, "manifest.json");
    expect(existsSync(path)).toBe(true);
    const m = JSON.parse(readFileSync(path, "utf8")) as {
      manifest_version: number;
      name: string;
      version: string;
      permissions: string[];
      host_permissions: string[];
      action?: { default_popup: string };
      background?: { service_worker: string; type?: string };
      content_scripts?: Array<{ matches: string[]; js: string[] }>;
    };
    expect(m.manifest_version).toBe(3);
    expect(m.name).toBe("RunMyCampus Companion");
    expect(typeof m.version).toBe("string");
    expect(Array.isArray(m.permissions)).toBe(true);
    expect(m.permissions).toEqual(
      expect.arrayContaining(["storage", "activeTab", "scripting"])
    );
    // 6 SIS vendor host patterns must be present (in any order).
    const hostBlob = m.host_permissions.join(" ");
    for (const vendor of [
      "powerschool.com",
      "blackbaud.com",
      "veracross.com",
      "getalma.com",
      "factsmgt.com",
      "skyward.com",
    ]) {
      expect(hostBlob).toContain(vendor);
    }
    expect(m.action?.default_popup).toBe("popup.html");
    // Background worker referenced (file may be a stub today; manifest
    // only requires the path string to be present.)
    expect(typeof m.background?.service_worker).toBe("string");
    expect(Array.isArray(m.content_scripts)).toBe(true);
  });

  it("tsconfig.json parses + declares strict mode + ES2022 target", () => {
    const path = resolve(rootDir, "tsconfig.json");
    expect(existsSync(path)).toBe(true);
    const ts = parseTolerantJson(readFileSync(path, "utf8")) as {
      compilerOptions: {
        strict: boolean;
        target: string;
        module: string;
        moduleResolution?: string;
        types?: string[];
      };
    };
    expect(ts.compilerOptions.strict).toBe(true);
    expect(ts.compilerOptions.target).toBe("ES2022");
    expect(ts.compilerOptions.module).toBe("ESNext");
    expect(ts.compilerOptions.types).toEqual(
      expect.arrayContaining(["chrome", "node"])
    );
  });

  it("vite config file is present on disk", () => {
    const path = resolve(rootDir, "vite.config.ts");
    expect(existsSync(path)).toBe(true);
    // Sanity: file should reference the defineConfig helper (so we know
    // we didn't ship an empty placeholder).
    const text = readFileSync(path, "utf8");
    expect(text).toContain("defineConfig");
    expect(text).toContain("rollupOptions");
  });
});
