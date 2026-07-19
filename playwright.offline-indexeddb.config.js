/**
 * Dedicated Playwright config for offline IndexedDB multiday E2E.
 *
 * Playwright 1.58 only honors top-level `webServer` (project-level
 * `webServer` is silently ignored) — hence this file instead of the
 * project entry in playwright.config.js.
 */
const path = require('path');
const { defineConfig } = require('@playwright/test');

const port = process.env.OFFLINE_E2E_PORT || '8777';

module.exports = defineConfig({
  testDir: 'tests/e2e',
  timeout: 60000,
  testMatch: '**/offline-multiday-indexeddb.spec.js',
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    channel: 'chromium',
    baseURL: `http://127.0.0.1:${port}`,
    serviceWorkers: 'block',
    launchOptions: {
      args: ['--proxy-server=direct://', '--proxy-bypass-list=*'],
    },
  },
  webServer: {
    command: 'node scripts/serve_offline_e2e_fixture.mjs',
    cwd: __dirname,
    env: {
      ...process.env,
      OFFLINE_E2E_PORT: port,
      OFFLINE_E2E_HOST: '127.0.0.1',
    },
    url: `http://127.0.0.1:${port}/offline-indexeddb-boot.html`,
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});
