// Playwright config for E2E tests (e.g. offline sync).
// Run: npx playwright install && npm run test:e2e
const { defineConfig } = require('@playwright/test');

// Chromium quirk: a single ruleset cannot both MAP apex runmycampus.com and tenant
// subdomains — apex MAP breaks *.tenant hosts; wildcard-only skips bare apex.
// Split projects: marketing uses apex MAP; tenant uses explicit tenant hosts + wildcard.
const _marketingHostRules = (
  process.env.PLAYWRIGHT_MARKETING_HOST_RULES ||
  'MAP runmycampus.com 127.0.0.1,MAP manager.runmycampus.com 127.0.0.1'
).trim();

const _tenantHostRules = (
  process.env.PLAYWRIGHT_TENANT_HOST_RULES ||
  'MAP example-school.runmycampus.com 127.0.0.1,' +
    'MAP demo-school.runmycampus.com 127.0.0.1,' +
    'MAP apple-class-qa.runmycampus.com 127.0.0.1,' +
    'MAP manager.runmycampus.com 127.0.0.1,' +
    'MAP *.runmycampus.com 127.0.0.1'
).trim();

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
      name: 'tenant-chromium',
      testMatch: ['**/parent-identity-cezgp-lane2.spec.js'],
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
