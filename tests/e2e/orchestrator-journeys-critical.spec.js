// @ts-check
// Orchestrator v5 critical journeys (optional — set ORCHESTRATOR_JOURNEY_E2E=1).
// Run: ORCHESTRATOR_JOURNEY_E2E=1 E2E_USERNAME=admin E2E_PASSWORD=Sch00l_1234 npx playwright test tests/e2e/orchestrator-journeys-critical.spec.js

const { test, expect } = require('@playwright/test');

const enabled = process.env.ORCHESTRATOR_JOURNEY_E2E === '1';
const TENANT_PREFIX = (process.env.TENANT_PREFIX || '/t/demo-school').replace(/\/$/, '');

async function tenantLogin(page) {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) {
    test.skip();
    return false;
  }
  await page.goto(`${TENANT_PREFIX}/authentication/login/`);
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /log in/i }).click();
  await page.waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), {
    timeout: 30000,
  });
  return true;
}

test.describe('Orchestrator v5 critical journeys', () => {
  test.beforeEach(() => {
    if (!enabled) test.skip();
  });

  test('staff backend dashboard loads without login trap', async ({ page }) => {
    if (!(await tenantLogin(page))) return;
    const response = await page.goto(`${TENANT_PREFIX}/authentication/backend/`);
    expect(response?.status()).toBeLessThan(400);
    await expect(page.locator('body')).not.toContainText(/sign in to continue/i);
  });

  test('help center reachable after login', async ({ page }) => {
    if (!(await tenantLogin(page))) return;
    const response = await page.goto(`${TENANT_PREFIX}/feedback/help/`);
    expect(response?.status()).toBeLessThan(400);
  });
});
