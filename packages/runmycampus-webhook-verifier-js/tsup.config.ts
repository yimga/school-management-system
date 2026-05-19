import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  // ES2020 matches package.json engines: node >= 16 (supports ES2020 in Node 14+).
  target: "es2020",
  splitting: false,
  // No external; we genuinely have zero runtime deps and we want the
  // bundle to be a single self-contained file (the `node:crypto`
  // import is a runtime probe via eval, not a static dependency).
  platform: "neutral",
  outDir: "dist",
});
