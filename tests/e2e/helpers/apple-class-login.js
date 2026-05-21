// @ts-check
const { execFileSync } = require('child_process');
const path = require('path');
const { expect } = require('@playwright/test');

const REPO_ROOT = path.join(__dirname, '..', '..', '..');
const TOTP_SCRIPT = path.join(REPO_ROOT, 'scripts', 'apple_class_qa_totp.py');

async function gotoWithRetry(page, url, options = {}) {
  const attempts = options.attempts || 6;
  const waitUntil = options.waitUntil || 'domcontentloaded';
  const timeout = options.timeout || 90000;
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await page.goto(url, { waitUntil, timeout });
    } catch (error) {
      lastError = error;
      const message = String(error?.message || error);
      if (!/ERR_CONNECTION|ERR_ABORTED|ECONNREFUSED/i.test(message) || attempt === attempts - 1) {
        throw error;
      }
      await page.waitForTimeout(2500);
    }
  }
  throw lastError;
}

function qaTotpToken(username) {
  return execFileSync('python', [TOTP_SCRIPT, username], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    env: process.env,
  }).trim();
}

/**
 * Sign in via the real login form; complete MFA verify when baseline roles require it.
 */
async function appleClassLogin(page, baseUrl, username, password) {
  await gotoWithRetry(page, `${baseUrl}/authentication/login/`);
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /log in/i }).click();
  await page.waitForLoadState('networkidle');

  let url = page.url();
  if (/\/authentication\/mfa\/setup/i.test(url)) {
    throw new Error(
      `MFA setup required for ${username}; run: python scripts/seed_apple_class_qa.py`,
    );
  }
  if (/\/authentication\/mfa\/verify/i.test(url)) {
    const token = qaTotpToken(username);
    await page.locator('input[name="token"]').fill(token);
    await page.getByRole('button', { name: /verify|continue|submit/i }).click();
    await page.waitForLoadState('networkidle');
    url = page.url();
    if (/\/authentication\/mfa\/setup/i.test(url)) {
      throw new Error(
        `MFA setup still required for ${username} after verify; run: python scripts/seed_apple_class_qa.py`,
      );
    }
  }

  expect(
    /\/authentication\/login\/?$/i.test(page.url()),
    `login completed for ${username}`,
  ).toBe(false);
}

module.exports = { appleClassLogin, qaTotpToken, gotoWithRetry };
