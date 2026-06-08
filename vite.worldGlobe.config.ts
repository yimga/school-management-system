import { defineConfig } from "vite";
import { readdirSync, unlinkSync } from "node:fs";
import { join, resolve } from "node:path";

const DIST_DIR = resolve(__dirname, "static/js/dist");
const RETIRED_CHUNK_PREFIX = "world-globe.vendor-";

/** Purge retired code-split vendor chunks before each build. */
function purgeRetiredGlobeChunks() {
  return {
    name: "purge-retired-globe-chunks",
    buildStart() {
      let names: string[] = [];
      try {
        names = readdirSync(DIST_DIR);
      } catch {
        return;
      }
      for (const name of names) {
        if (name.startsWith(RETIRED_CHUNK_PREFIX)) {
          unlinkSync(join(DIST_DIR, name));
        }
      }
    },
  };
}

/** Single-file ES bundle — production manifest hashing must not break relative chunk imports. */
export default defineConfig({
  plugins: [purgeRetiredGlobeChunks()],
  build: {
    outDir: "static/js/dist",
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, "src/apps/worldGlobe/mount.ts"),
      output: {
        format: "es",
        entryFileNames: "world-globe.mount.js",
        inlineDynamicImports: true,
      },
    },
  },
});
