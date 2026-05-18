#!/usr/bin/env node
/**
 * Create Playwright storage state for manager visual QA (run before E2E).
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const {
  loginManager,
  AUTH_STATE_PATH,
  MANAGER_BASE_URL,
  MANAGER_HOST,
} = require('../tests/e2e/helpers/manager-login');

const MANAGER_PORT = process.env.VISUAL_QA_PORT || '8012';
const baseURL =
  process.env.MANAGER_BASE_URL || `http://${MANAGER_HOST}:${MANAGER_PORT}`;
const hostRules =
  process.env.PLAYWRIGHT_HOST_RULES || 'MAP manager.runmycampus.com 127.0.0.1';

async function main() {
  fs.mkdirSync(path.dirname(AUTH_STATE_PATH), { recursive: true });
  const browser = await chromium.launch({
    channel: 'chromium',
    args: [`--host-resolver-rules=${hostRules}`],
  });
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1400, height: 900 },
  });
  const page = await context.newPage();
  await loginManager(page, {
    username: process.env.VISUAL_QA_USERNAME || 'visualqa_admin',
    password: process.env.VISUAL_QA_PASSWORD || 'VisualQaPass123!',
  });
  await context.storageState({ path: AUTH_STATE_PATH });
  await browser.close();
  console.log(`Wrote ${AUTH_STATE_PATH}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
