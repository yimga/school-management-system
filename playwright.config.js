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
  // Local dev uses plain HTTP; prevent Chrome from upgrading *.runmycampus.com.
  '--disable-features=HttpsUpgrades,HttpsFirstMode',
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
      name: 'globe-preview-chromium',
      testMatch: ['**/world-globe-preview-offline.spec.js'],
      use: {
        channel: 'chromium',
        baseURL: process.env.GLOBE_PREVIEW_BASE_URL || 'http://127.0.0.1:8765',
        serviceWorkers: 'block',
      },
      webServer: {
        command: 'node scripts/serve_globe_preview_static.mjs',
        cwd: __dirname,
        url: 'http://127.0.0.1:8765/artifacts/global-footprint-section-preview.html',
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },
    },
    {
      name: 'manager-chromium',
      testMatch: [
        '**/manager-bulk-confirm-dialog.spec.js',
        '**/manager-surface-parity.spec.js',
        '**/manager-theme-visibility.spec.js',
        '**/control-plane-layout-audit.spec.js',
        '**/copilot-rail-grid.spec.js',
        '**/world-globe-online-offline.spec.js',
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
      name: 'tenant-phase-chromium',
      testMatch: [
        '**/phase1-architecture-navigation.spec.js',
        '**/phase2-portal-navigation.spec.js',
      ],
      timeout: 90000,
      use: {
        channel: 'chromium',
        baseURL:
          process.env.PLAYWRIGHT_TENANT_BASE_URL ||
          `http://127.0.0.1:${_managerPort}/t/demo-school`,
        serviceWorkers: 'block',
        launchOptions: {
          args: ['--proxy-server=direct://', '--proxy-bypass-list=*'],
        },
      },
      webServer: {
        command: 'bash scripts/run_playwright_tenant_e2e_server.sh',
        cwd: __dirname,
        url: `http://127.0.0.1:${_managerPort}/t/demo-school/authentication/login/`,
        reuseExistingServer: !process.env.CI,
        timeout: 240000,
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
          (process.env.TENANT_E2E_SUBDOMAIN === '1'
            ? `http://demo-school.runmycampus.com:${_managerPort}`
            : `http://127.0.0.1:${_managerPort}/t/demo-school`),
        launchOptions: {
          args:
            process.env.TENANT_E2E_SUBDOMAIN === '1'
              ? _chromiumArgs(_tenantHostRules)
              : ['--proxy-server=direct://', '--proxy-bypass-list=*'],
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
