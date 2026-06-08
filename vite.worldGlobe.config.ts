import { defineConfig } from "vite";
import { resolve } from "node:path";

/** Code-split three.js + globe.gl from mount entry (batch 1651 perf slice). */
export default defineConfig({
  build: {
    outDir: "static/js/dist",
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, "src/apps/worldGlobe/mount.ts"),
      output: {
        format: "es",
        entryFileNames: "world-globe.mount.js",
        chunkFileNames: "world-globe.[name].js",
        manualChunks(id) {
          if (id.includes("node_modules/three")) return "vendor-three";
          if (id.includes("node_modules/globe.gl")) return "vendor-gl";
        },
      },
    },
  },
});
