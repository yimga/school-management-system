import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "static/js/dist",
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, "src/apps/luxWorkspace/mount.tsx"),
      name: "RmcLuxWorkspace",
      formats: ["iife"],
      fileName: () => "lux-workspace.mount.js",
    },
    rollupOptions: {
      output: {
        assetFileNames: "lux-workspace.[ext]",
      },
    },
  },
});
