// @ts-check
// Interaction integrity: profile dropdown logout visible + help center route.
// Run: E2E_USERNAME=admin E2E_PASSWORD=Sch00l_1234 npx playwright test tests/e2e/interaction-integrity.spec.js

const { test, expect } = require('@playwright/test');

const TENANT_PREFIX = (process.env.TENANT_PREFIX || '/t/demo-school').replace(/\/$/, '');
const LOGIN_PATH = `${TENANT_PREFIX}/authentication/login/`;

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
  await page.waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), {
    timeout: 20000,
  });
  return true;
}

test('user dropdown logout is visible at 320px viewport', async ({ page }) => {
  if (!(await tenantLogin(page))) return;
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto(`${TENANT_PREFIX}/authentication/backend/`);
  await page.locator('#userDropdownBtn').click();
  const menu = page.locator('.user-dropdown-menu.show');
  await expect(menu).toBeVisible({ timeout: 5000 });
  const logout = menu.getByRole('link', { name: /logout/i });
  await expect(logout).toBeVisible();
  await expect(logout).toHaveAttribute('href', /logout/);
  const box = await logout.boundingBox();
  const menuBox = await menu.boundingBox();
  expect(box).toBeTruthy();
  expect(menuBox).toBeTruthy();
  if (box && menuBox) {
    expect(box.y + box.height).toBeLessThanOrEqual(menuBox.y + menuBox.height + 2);
  }
});

test('help center route returns 200 for staff', async ({ page }) => {
  if (!(await tenantLogin(page))) return;
  const response = await page.goto(`${TENANT_PREFIX}/feedback/help/`);
  expect(response?.status()).toBeLessThan(400);
  await expect(page.locator('body')).toContainText(/help/i);
});
