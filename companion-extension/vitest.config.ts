/**
 * Vitest config — jsdom environment (popup DOM + chrome.storage mock).
 *
 * Shares aliases with vite.config.ts via duplicated `resolve.alias`. We
 * intentionally don't re-import vite.config to keep test-runner startup
 * cheap and free of build-plugin side-effects (vite's `closeBundle`
 * hook would fire in test mode if we merged the configs).
 */
import { defineConfig } from "vitest/config";
import { resolve } from "node:path";

const srcDir = resolve(__dirname, "src");

export default defineConfig({
  resolve: {
    alias: {
      "~/lib": resolve(srcDir, "lib"),
      "~/popup": resolve(srcDir, "popup"),
      "~/content": resolve(srcDir, "content"),
      "~/background": resolve(srcDir, "background"),
      "~/vendors": resolve(srcDir, "vendors"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
    },
  },
});
