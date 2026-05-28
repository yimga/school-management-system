// Playwright config for E2E tests (e.g. offline sync).
// Run: npx playwright install && npm run test:e2e
const path = require('path');
const { defineConfig } = require('@playwright/test');

const _managerStorageState = path.join(
  __dirname,
  'artifacts/manager-playwright-auth.json',
);

// Chromium quirk: a single ruleset cannot both MAP apex runmycampus.com and tenant
// subdomains — apex MAP breaks *.tenant hosts; wildcard-only skips bare apex.
// Split projects: marketing uses apex MAP; tenant uses explicit tenant hosts + wildcard.
const _marketingHostRules = (
  process.env.PLAYWRIGHT_MARKETING_HOST_RULES ||
  'MAP runmycampus.com 127.0.0.1,MAP manager.runmycampus.com 127.0.0.1'
).trim();

const _managerHostRules = (
  process.env.PLAYWRIGHT_HOST_RULES || 'MAP manager.runmycampus.com 127.0.0.1'
).trim();

const _tenantHostRules = (
  process.env.PLAYWRIGHT_TENANT_HOST_RULES ||
  'MAP example-school.runmycampus.com 127.0.0.1,' +
    'MAP demo-school.runmycampus.com 127.0.0.1,' +
    'MAP apple-class-qa.runmycampus.com 127.0.0.1,' +
    'MAP manager.runmycampus.com 127.0.0.1,' +
    'MAP *.runmycampus.com 127.0.0.1'
).trim();

const _managerPort = process.env.VISUAL_QA_PORT || '8012';
const _managerBaseUrl =
  process.env.MANAGER_BASE_URL ||
  `http://manager.runmycampus.com:${_managerPort}`;

const _chromiumArgs = (hostRules) => [
  `--host-resolver-rules=${hostRules}`,
  '--proxy-server=direct://',
  '--proxy-bypass-list=*',
];

module.exports = defineConfig({
  testDir: 'tests/e2e',
  timeout: 45000,
  use: {
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'marketing-chromium',
      testMatch: [
        '**/marketing-visual-engine.spec.js',
        '**/help-ai-center-a11y.spec.js',
      ],
      use: {
        channel: 'chromium',
        baseURL: process.env.MARKETING_BASE_URL || 'http://runmycampus.com:8000',
        launchOptions: {
          args: _chromiumArgs(_marketingHostRules),
        },
      },
    },
    {
      name: 'manager-chromium',
      testMatch: [
        '**/manager-bulk-confirm-dialog.spec.js',
        '**/manager-surface-parity.spec.js',
        '**/manager-theme-visibility.spec.js',
      ],
      use: {
        channel: 'chromium',
        baseURL: _managerBaseUrl,
        storageState: _managerStorageState,
        serviceWorkers: 'block',
        launchOptions: {
          args: _chromiumArgs(_managerHostRules),
        },
      },
    },
    {
      name: 'tenant-chromium',
      testMatch: [
        '**/parent-identity-cezgp-lane2.spec.js',
        '**/tablet-dashboard-visual.spec.js',
      ],
      use: {
        channel: 'chromium',
        baseURL:
          process.env.PLAYWRIGHT_TENANT_BASE_URL ||
          'http://demo-school.runmycampus.com:8000',
        launchOptions: {
          args: _chromiumArgs(_tenantHostRules),
        },
      },
    },
    {
      name: 'chromium',
      testIgnore: [
        '**/marketing-visual-engine.spec.js',
        '**/help-ai-center-a11y.spec.js',
        '**/parent-identity-cezgp-lane2.spec.js',
        '**/tablet-dashboard-visual.spec.js',
        '**/manager-bulk-confirm-dialog.spec.js',
        '**/manager-surface-parity.spec.js',
        '**/manager-theme-visibility.spec.js',
      ],
      use: {
        channel: 'chromium',
        baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000',
        launchOptions: {
          args: _chromiumArgs(
            process.env.PLAYWRIGHT_HOST_RULES || _tenantHostRules,
          ),
        },
      },
    },
  ],
});
