/**
 * Vite build config for RunMyCampus Companion (MV3 extension).
 *
 * Hand-rolled multi-entry rollup config — avoids the @crxjs/vite-plugin
 * dependency so the operator can `npm install` with zero plugin churn
 * across vite major versions. Builds three independent entries:
 *
 *   - popup       → dist/popup.js          (loaded by popup.html)
 *   - background  → dist/service_worker.js (Manifest V3 background SW)
 *   - content     → dist/content_script.js (injected into SIS tabs)
 *
 * On `vite build` we ALSO copy manifest.json + popup.html into `dist/`
 * so the operator can load-unpacked from `dist/` directly. Icons under
 * `icons/` are copied into `dist/icons/`.
 *
 * Aliases mirror tsconfig.json's `paths` so `import "~/lib/..."` resolves
 * identically at type-check time and at bundle time.
 */
import { defineConfig } from "vite";
import { resolve } from "node:path";
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

const rootDir = __dirname;
const srcDir = resolve(rootDir, "src");

// Build target selector. Set MODE=firefox (or pass `--mode firefox`)
// to produce dist-firefox/ with manifest.firefox.json instead of the
// Chrome-targeted manifest.json. Default is Chrome/Edge (identical zip).
const buildMode = process.env.MODE === "firefox" ? "firefox" : "chrome";
const distDir = resolve(rootDir, buildMode === "firefox" ? "dist-firefox" : "dist");
const manifestSourceName = buildMode === "firefox" ? "manifest.firefox.json" : "manifest.json";

export default defineConfig({
  root: rootDir,
  publicDir: false,
  resolve: {
    alias: {
      "~/lib": resolve(srcDir, "lib"),
      "~/popup": resolve(srcDir, "popup"),
      "~/content": resolve(srcDir, "content"),
      "~/background": resolve(srcDir, "background"),
      "~/vendors": resolve(srcDir, "vendors"),
    },
  },
  build: {
    outDir: distDir,
    emptyOutDir: true,
    sourcemap: true,
    target: "es2022",
    rollupOptions: {
      input: {
        popup: resolve(srcDir, "popup", "popup.ts"),
        // background + content entries are referenced in manifest.json;
        // we only declare them here if the source files exist on disk.
        // (Stubs ship in src/background/ and src/content/ — see README.)
        background: resolve(srcDir, "background", "service_worker.ts"),
        content: resolve(srcDir, "content", "content_script.ts"),
      },
      output: {
        // Flat output names so manifest.json paths stay stable.
        entryFileNames: (chunk) => {
          if (chunk.name === "popup") return "popup.js";
          if (chunk.name === "background") return "service_worker.js";
          if (chunk.name === "content") return "content_script.js";
          return "[name].js";
        },
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
        format: "es",
      },
    },
  },
  plugins: [
    {
      name: "rmc-companion-copy-static",
      closeBundle() {
        if (!existsSync(distDir)) mkdirSync(distDir, { recursive: true });
        const manifestPath = resolve(rootDir, manifestSourceName);
        if (existsSync(manifestPath)) {
          const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
          if (manifest.background?.service_worker) {
            manifest.background.service_worker = "service_worker.js";
          }
          for (const script of manifest.content_scripts ?? []) {
            if (Array.isArray(script.js)) {
              script.js = ["content_script.js"];
            }
          }
          writeFileSync(
            resolve(distDir, "manifest.json"),
            `${JSON.stringify(manifest, null, 2)}\n`,
            "utf8"
          );
        }
        const popupPath = resolve(rootDir, "popup.html");
        if (existsSync(popupPath)) {
          const popupHtml = readFileSync(popupPath, "utf8").replace(
            'src="src/popup/popup.ts"',
            'src="popup.js"'
          );
          writeFileSync(resolve(distDir, "popup.html"), popupHtml, "utf8");
        }
        const iconsDir = resolve(rootDir, "icons");
        if (existsSync(iconsDir)) {
          cpSync(iconsDir, resolve(distDir, "icons"), { recursive: true });
        }
      },
    },
  ],
});
