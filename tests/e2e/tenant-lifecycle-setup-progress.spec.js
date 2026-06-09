// @ts-check
/**
 * Phase 14 — tenant lifecycle setup progress (inactive subdomain + progress API contract).
 *
 * Requires Django on 8000 and an inactive tenant slug:
 *   SIGNUP_E2E_INACTIVE_SLUG=demo-school npm run test:e2e:tenant-lifecycle-setup
 */
const { test, expect } = require('@playwright/test');

const INACTIVE_SLUG = (process.env.SIGNUP_E2E_INACTIVE_SLUG || 'demo-school').trim();
const INACTIVE_HOST = `${INACTIVE_SLUG}.runmycampus.com`;
const LOCAL_DNS_MAP = (process.env.SIGNUP_E2E_LOCAL_DNS_MAP || '1').trim() === '1';
const BASE = (process.env.SIGNUP_E2E_BASE_URL || 'http://runmycampus.com:8000').replace(/\/$/, '');

if (LOCAL_DNS_MAP) {
  test.use({
    launchOptions: {
      args: [
        '--host-resolver-rules=MAP runmycampus.com 127.0.0.1, MAP *.runmycampus.com 127.0.0.1',
      ],
    },
  });
}

test('inactive tenant setup page shows live provision progress UI', async ({ page, context }) => {
  const inactiveBase = `http://${INACTIVE_HOST}:8000`;
  const response = await page.goto(`${inactiveBase}/`, { waitUntil: 'domcontentloaded' });
  expect(response).not.toBeNull();
  expect([200, 202]).toContain(response.status());

  await expect(page.getByText(/setting up|preparing|portal/i).first()).toBeVisible({
    timeout: 15000,
  });
  await expect(page.locator('[data-rmc-provision-progress]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-rmc-provision-bar]')).toHaveAttribute(
    'aria-valuenow',
    /^\d+$/,
  );

  const apiResponse = await context.request.get(
    'http://127.0.0.1:8000/api/pending-provision/progress/',
    { headers: { Host: INACTIVE_HOST } },
  );
  expect(apiResponse.ok()).toBeTruthy();
  const payload = await apiResponse.json();
  expect(payload.ok).toBeTruthy();
  expect(payload.workflow_key).toBe('tenant_school_provision');
  expect(Array.isArray(payload.steps)).toBeTruthy();
  expect(payload.steps.length).toBeGreaterThanOrEqual(5);
  expect(Array.isArray(payload.extended_steps)).toBeTruthy();
  expect(payload.extended_step_count).toBe(14);
  expect(payload.extended_steps.length).toBe(14);
});
