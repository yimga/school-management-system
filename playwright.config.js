// Playwright config for E2E tests (e.g. offline sync).
// Run: npx playwright install && npm run test:e2e
// Base URL: start Django with offline mode enabled (SITE.enable_offline_mode=True).
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: 'tests/e2e',
  timeout: 30000,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { channel: 'chromium' } }],
});
