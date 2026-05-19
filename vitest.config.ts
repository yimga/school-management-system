import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@analytics": resolve(__dirname, "src/components/shared/analytics"),
      "@navigation": resolve(__dirname, "src/components/shared/navigation"),
      "@dashboard": resolve(__dirname, "src/apps/dashboard"),
      "@seeds": resolve(__dirname, "src/database/seeds"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    include: [
      "src/**/*.test.ts",
      "src/**/*.test.tsx",
      "tests/**/*.test.ts",
      "tests/**/*.test.tsx",
    ],
    css: true,
  },
});
