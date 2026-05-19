import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@analytics": resolve(__dirname, "src/components/shared/analytics"),
      "@dashboard": resolve(__dirname, "src/apps/dashboard"),
      "@seeds": resolve(__dirname, "src/database/seeds"),
    },
  },
  build: {
    outDir: "static/js/dist",
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, "src/apps/dashboard/mount.tsx"),
      name: "RmcAnalyticsDashboard",
      formats: ["iife"],
      fileName: "rmc-analytics-dashboard",
    },
    rollupOptions: {
      output: {
        assetFileNames: "rmc-analytics-dashboard.[ext]",
      },
    },
  },
});
