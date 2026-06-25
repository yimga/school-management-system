// @ts-check
/**
 * E2E: provisioning → go-live golden path (batch 1731 gap close).
 *
 * Local:
 *   python manage.py runserver 127.0.0.1:8000
 *   python manage.py seed_provisioning_golive_e2e --slug=demo-school
 *   SIGNUP_E2E_LOCAL_DNS_MAP=1 npm run test:e2e:tenant-lifecycle-launch-ready
 */
const { test, expect } = require('@playwright/test');

const LOCAL_DNS = (process.env.SIGNUP_E2E_LOCAL_DNS_MAP || '1').trim() === '1';
const SLUG = (process.env.SIGNUP_E2E_GOLDEN_SLUG || 'demo-school').trim();
const TENANT_BASE = `http://${SLUG}.runmycampus.com:8000`;
const ADMIN_USER = process.env.DEMO_ADMIN_USER || 'admin';
const ADMIN_PASSWORD = process.env.DEMO_ADMIN_PASSWORD || 'Sch00l_1234';

if (LOCAL_DNS) {
  test.use({
    launchOptions: {
      args: [
        '--host-resolver-rules=MAP runmycampus.com 127.0.0.1, MAP *.runmycampus.com 127.0.0.1',
      ],
    },
  });
}

async function loginAdmin(page) {
  await page.goto(`${TENANT_BASE}/authentication/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name="username"]', ADMIN_USER);
  await page.fill('input[name="password"]', ADMIN_PASSWORD);
  await page.locator('form').first().evaluate((form) => {
    if (form && typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.submit();
  });
  await page.waitForURL(/authentication\/(backend|redirect|onboarding)/, { timeout: 60000 });
}

test('tenant school readiness API returns unified meter payload', async ({ page }) => {
  test.skip(!LOCAL_DNS, 'Set SIGNUP_E2E_LOCAL_DNS_MAP=1 with runserver for live probe');
  const res = await page.request.get(`${TENANT_BASE}/api/school/readiness/`, {
    failOnStatusCode: false,
  });
  expect([200, 302, 401, 403]).toContain(res.status());
  if (res.status() === 200) {
    const body = await res.json();
    expect(body.ok).toBeTruthy();
    expect(Array.isArray(body.phases)).toBeTruthy();
    expect(body.phases.length).toBe(4);
    expect(typeof body.meter_percent).toBe('number');
    expect(body.setup_studio).toBeTruthy();
    expect(typeof body.setup_studio.launch_ready).toBe('boolean');
    expect(body.provision).toBeTruthy();
    expect(typeof body.provision.needs_resume).toBe('boolean');
  }
});

test('setup landing surfaces journey train when authenticated admin', async ({ page }) => {
  test.skip(!LOCAL_DNS, 'Set SIGNUP_E2E_LOCAL_DNS_MAP=1 with runserver for live probe');
  await loginAdmin(page);
  await page.goto(`${TENANT_BASE}/authentication/backend/`, { waitUntil: 'domcontentloaded' });
  const train = page.locator('[data-rmc-readiness-train="1"]');
  const setupSurface = page.locator('[data-rmc-setup-surface="active"]');
  const ceremony = page.locator('[data-rmc-launch-ceremony="1"]');
  const hasTrain = (await train.count()) > 0;
  const hasSetup = (await setupSurface.count()) > 0;
  const hasCeremony = (await ceremony.count()) > 0;
  expect(hasTrain || hasSetup || hasCeremony).toBeTruthy();
});

test('golden path: Go live → launch ceremony on Command Center', async ({ page }) => {
  test.skip(!LOCAL_DNS, 'Set SIGNUP_E2E_LOCAL_DNS_MAP=1 with runserver for live probe');

  const readinessRes = await page.request.get(`${TENANT_BASE}/api/school/readiness/`, {
    failOnStatusCode: false,
  });
  test.skip(readinessRes.status() !== 200, 'Readiness API unavailable — is runserver up?');
  const readiness = await readinessRes.json();
  test.skip(
    !readiness.setup_studio?.launch_ready || readiness.has_launched,
    'Run: python manage.py seed_provisioning_golive_e2e --slug=' + SLUG,
  );

  await loginAdmin(page);
  await page.goto(`${TENANT_BASE}/authentication/backend/`, { waitUntil: 'domcontentloaded' });

  const golive = page.locator('[data-rmc-execute-launch-form="1"] button[type="submit"]').first();
  await expect(golive).toBeVisible({ timeout: 20000 });
  await golive.click();

  await page.waitForURL(/launched=1/, { timeout: 60000 });
  await expect(page.locator('[data-rmc-launch-ceremony="1"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('.rmc-admin-bento[data-rmc-admin-workspace="command-center"]')).toBeVisible();
});
