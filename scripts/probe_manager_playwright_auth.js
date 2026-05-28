#!/usr/bin/env node
/** Quick probe: storage state reaches /super/schools/ on manager host. */
const fs = require('fs');
const { chromium } = require('playwright');
const { AUTH_STATE_PATH, MANAGER_BASE_URL } = require('../tests/e2e/helpers/manager-login');

const hostRules =
  process.env.PLAYWRIGHT_HOST_RULES || 'MAP manager.runmycampus.com 127.0.0.1';

async function main() {
  if (!fs.existsSync(AUTH_STATE_PATH)) {
    console.error(`FAIL: missing ${AUTH_STATE_PATH}`);
    process.exit(1);
  }
  const browser = await chromium.launch({
    channel: 'chromium',
    args: [
      `--host-resolver-rules=${hostRules}`,
      '--proxy-server=direct://',
      '--proxy-bypass-list=*',
    ],
  });
  const playwrightUa =
    process.env.VISUAL_QA_USER_AGENT ||
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
  const context = await browser.newContext({
    baseURL: MANAGER_BASE_URL,
    storageState: AUTH_STATE_PATH,
    userAgent: playwrightUa,
    viewport: { width: 1400, height: 900 },
  });
  const cookies = await context.cookies();
  console.log(
    'context cookies',
    cookies.map((c) => `${c.name}@${c.domain || c.url}`).join(', '),
  );
  const page = await context.newPage();
  const response = await page.goto('/super/schools/', {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  const url = page.url();
  const bulkCount = await page.locator('table[data-rmc-list-bulk="1"]').count();
  await browser.close();
  console.log('status', response?.status(), 'url', url, 'bulk_tables', bulkCount);
  if (bulkCount < 1) {
    console.error('FAIL: not authenticated on schools list');
    process.exit(1);
  }
  console.log('OK: manager auth probe');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
