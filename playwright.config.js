// @ts-check
// Playwright config for smoke E2E tests. Run: npx playwright test
// First time: npx playwright install

const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: process.env.CI ? undefined : {
    command: 'python manage.py runserver 8000',
    url: 'http://localhost:8000/authentication/login/',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});
