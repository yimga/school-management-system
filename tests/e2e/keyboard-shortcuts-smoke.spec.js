// @ts-check
// Keyboard shortcuts smoke: cheatsheet overlay, filter, inbox keys on notifications.
// Run: E2E_USERNAME=admin E2E_PASSWORD=Sch00l_1234 npx playwright test tests/e2e/keyboard-shortcuts-smoke.spec.js
// Tenant path prefix (default demo-school): TENANT_PREFIX=/t/demo-school

const { test, expect } = require('@playwright/test');

const TENANT_PREFIX = (process.env.TENANT_PREFIX || '/t/demo-school').replace(/\/$/, '');
const LOGIN_PATH = `${TENANT_PREFIX}/authentication/login/`;
const NOTIFICATIONS_PATH = `${TENANT_PREFIX}/authentication/notifications/`;

async function tenantLogin(page) {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) {
    test.skip();
    return false;
  }
  await page.goto(LOGIN_PATH);
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /log in/i }).click();
  await page.waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), { timeout: 20000 });
  return true;
}

test('question mark opens keyboard shortcuts overlay', async ({ page }) => {
  if (!(await tenantLogin(page))) return;
  await page.goto(`${TENANT_PREFIX}/authentication/backend/`);
  await expect(page.locator('[data-rmc-page], .portal-body-with-layout, body')).toBeVisible({ timeout: 15000 });
  await page.keyboard.press('?');
  const dialog = page.locator('dialog.rmc-kbd-cheatsheet');
  await expect(dialog).toBeVisible({ timeout: 5000 });
  await expect(dialog.locator('[data-rmc-kbd-grid]')).toBeVisible();
});

test('shortcuts filter narrows visible rows', async ({ page }) => {
  if (!(await tenantLogin(page))) return;
  await page.goto(`${TENANT_PREFIX}/authentication/backend/`);
  await page.keyboard.press('?');
  const dialog = page.locator('dialog.rmc-kbd-cheatsheet');
  await expect(dialog).toBeVisible({ timeout: 5000 });
  const filter = dialog.locator('[data-rmc-kbd-filter]');
  const rowsBefore = await dialog.locator('[data-rmc-kbd-grid] li').count();
  expect(rowsBefore).toBeGreaterThan(0);
  await filter.fill('search');
  const rowsAfter = await dialog.locator('[data-rmc-kbd-grid] li').count();
  expect(rowsAfter).toBeGreaterThan(0);
  expect(rowsAfter).toBeLessThan(rowsBefore);
});

test('inbox page responds to U and A filter shortcuts', async ({ page }) => {
  if (!(await tenantLogin(page))) return;
  await page.goto(NOTIFICATIONS_PATH);
  await expect(page.locator('[data-rmc-page="notifications-inbox"]')).toBeVisible({ timeout: 15000 });
  await page.keyboard.press('u');
  await expect(page).toHaveURL(/status=unread/);
  await page.goto(NOTIFICATIONS_PATH);
  await page.keyboard.press('a');
  await expect(page).not.toHaveURL(/status=unread/);
});
