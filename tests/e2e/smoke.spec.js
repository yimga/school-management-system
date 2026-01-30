// @ts-check
// Smoke E2E: login page loads, and (if credentials provided) login → backend dashboard.
// Run: npx playwright test
// With server already running: BASE_URL=http://localhost:8000 npx playwright test

const { test, expect } = require('@playwright/test');

test('login page loads', async ({ page }) => {
  await page.goto('/accounts/login/');
  await expect(page).toHaveTitle(/login|sign in|portal/i);
  await expect(page.getByRole('heading', { name: /log in|sign in/i }).or(page.locator('input[name="username"]'))).toBeVisible({ timeout: 10000 });
});

test('backend dashboard reachable after login', async ({ page }) => {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) {
    test.skip();
    return;
  }
  await page.goto('/accounts/login/');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(accounts\/redirect|portal|backend|teacher|parent)/, { timeout: 15000 });
  await page.goto('/authentication/backend/');
  await expect(page.locator('body.portal-backend, [data-backend-theme], .page-wrap')).toBeVisible({ timeout: 10000 });
});
