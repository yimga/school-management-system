// Playwright config for E2E tests (e.g. offline sync).
// Run: npx playwright install && npm run test:e2e
// Base URL: start Django with offline mode enabled (SITE.enable_offline_mode=True).
const { defineConfig } = require('@playwright/test');

// run_visual_qa.sh sets PLAYWRIGHT_HOST_RULES when a Postgres tenant domain is discovered
const _defaultRules =
  'MAP gilead-school.runmycampus.com 127.0.0.1,MAP demo-school.runmycampus.com 127.0.0.1,MAP *.runmycampus.com 127.0.0.1,MAP runmycampus.com 127.0.0.1,MAP manager.runmycampus.com 127.0.0.1,MAP apple-class-qa.runmycampus.com 127.0.0.1';
const _hostRules = (process.env.PLAYWRIGHT_HOST_RULES || _defaultRules).trim();

module.exports = defineConfig({
  testDir: 'tests/e2e',
  timeout: 45000,
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000',
    trace: 'on-first-retry',
  },
  projects: [{
    name: 'chromium',
    use: {
      channel: 'chromium',
      launchOptions: {
        args: [`--host-resolver-rules=${_hostRules}`],
      },
    },
  }],
});
