// @ts-check
/**
 * Browser validation for the 2026-08-02 Admin Home "command cockpit" work.
 *
 * Boot a tenant server yourself (RMC_E2E_EXTERNAL_SERVER=1) with the PROVEN recipe
 * (threaded runserver + DJANGO_SQLITE_TIMEOUT=90 + LOGIN_POW_ENABLED=0), then:
 *   VISUAL_QA_PORT=8013 VISUAL_QA_TENANT_PHASE_PORT=8013 TENANT_E2E_SUBDOMAIN=1 \
 *   E2E_TENANT_USER=demo.admin E2E_TENANT_PASSWORD=Test1234 \
 *   VISUAL_QA_TOTP_HEX_KEY=<demo hex> DB_FILE=<db> RMC_E2E_EXTERNAL_SERVER=1 \
 *   npx playwright test tests/e2e/cockpit-sticky-slideover.spec.js --project=chromium --workers=1
 *
 * Validates, on the real authenticated Admin Home, the SHIPPED cockpit fixes:
 *   1. the activation-checklist CTA is a real, affordant button (bg + border + padding)
 *   2. the Phase-8 "ROLE_HOME" intent strip is retired from the visible surface
 *   3. the appearance/style picker is collapsed behind a disclosure by default
 *
 * NOTE — the "sticky command header" your-call item is intentionally NOT shipped:
 * the backend dashboard scrolls inside an inner column (.portal-main-col) and the
 * command band lives in a bounded grid cell (.page-wrap.rmc-shell-content-grid,
 * ~546px), so position:sticky only pins for ~one screen then releases. Making it
 * pin throughout needs a shell layout restructure (lift the band out of the grid
 * cell), which is out of scope for a safe, scoped change. Diagnosed in-browser
 * 2026-08-02 (relTop 32 -> -173 at scrollTop 655).
 */
const { test, expect } = require('@playwright/test');
const {
  loginTenant,
  ensureTenantCanonicalHost,
  TENANT_BASE_URL,
} = require('./helpers/tenant-login');

test.setTimeout(180000);

async function gotoAdminHome(page) {
  await page.goto(`${TENANT_BASE_URL}/authentication/backend/`, {
    waitUntil: 'domcontentloaded',
    timeout: 120000,
  });
  await ensureTenantCanonicalHost(page);
  await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => {});
  await expect(page).toHaveTitle(/Admin Home/i);
}

test('checklist CTA renders as a real button, not a bare link', async ({ page }) => {
  await loginTenant(page, { username: 'demo.admin', password: 'Test1234' });
  await gotoAdminHome(page);

  const btn = page.locator('a.rmc-setup-surface__all').first();
  await expect(btn).toHaveCount(1);
  const style = await btn.evaluate((el) => {
    const cs = getComputedStyle(el);
    return {
      display: cs.display,
      padTop: parseFloat(cs.paddingTop),
      padLeft: parseFloat(cs.paddingLeft),
      borderTop: parseFloat(cs.borderTopWidth),
      bg: cs.backgroundColor,
      radius: parseFloat(cs.borderTopLeftRadius),
      height: el.getBoundingClientRect().height,
    };
  });
  expect(style.display).toContain('flex'); // inline-flex
  expect(style.padTop).toBeGreaterThan(4);
  expect(style.padLeft).toBeGreaterThan(6);
  expect(style.borderTop).toBeGreaterThan(0);
  expect(style.bg).not.toBe('rgba(0, 0, 0, 0)');
  expect(style.bg).not.toBe('transparent');
  expect(style.radius).toBeGreaterThan(0);
  expect(style.height).toBeGreaterThan(28);
  await expect(btn.locator('i.bi-check2-square')).toHaveCount(1);
});

test('Phase-8 ROLE_HOME intent strip is retired from the visible surface', async ({ page }) => {
  await loginTenant(page, { username: 'demo.admin', password: 'Test1234' });
  await gotoAdminHome(page);

  const strip = page.locator('.phase8-declaration-strip').first();
  await expect(strip).toHaveCount(1); // still in the DOM (coverage/a11y contract)
  const info = await strip.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return { w: r.width, h: r.height, position: cs.position, clip: cs.clip };
  });
  expect(info.h).toBeLessThanOrEqual(2); // clipped, not a full-height card
  expect(info.w).toBeLessThanOrEqual(2);
  await expect(page.getByText('ROLE_HOME', { exact: true })).toHaveCount(0);
});

test('appearance/style picker is collapsed behind a disclosure by default', async ({ page }) => {
  await loginTenant(page, { username: 'demo.admin', password: 'Test1234' });
  await gotoAdminHome(page);

  const disclosure = page.locator('details.rmc-setup-style-strip__disclosure').first();
  if ((await disclosure.count()) === 0) {
    test.skip(true, 'style strip not present on this surface state');
    return;
  }
  expect(await disclosure.evaluate((el) => el.hasAttribute('open'))).toBe(false);
  const firstChip = disclosure.locator('.rmc-setup-style-strip__chip').first();
  if (await firstChip.count()) {
    await expect(firstChip).not.toBeVisible();
    await disclosure.locator('summary').click();
    await expect(firstChip).toBeVisible();
  }
});
