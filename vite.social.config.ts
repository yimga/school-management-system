import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "static/js/dist",
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, "src/apps/socialFeed/mount.tsx"),
      name: "RmcSocialFeed",
      formats: ["iife"],
      fileName: () => "social-feed.mount.js",
    },
    rollupOptions: {
      output: {
        assetFileNames: "social-feed.[ext]",
      },
    },
  },
});
