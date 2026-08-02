// @ts-check
/**
 * Browser validation for the 2026-08-02 Admin Home "command cockpit" work.
 *
 * Boot a tenant server yourself (RMC_E2E_EXTERNAL_SERVER=1) with the PROVEN recipe
 * (threaded runserver + DJANGO_SQLITE_TIMEOUT=90 + LOGIN_POW_ENABLED=0). IMPORTANT: put
 * the SQLite DB_FILE on NON-OneDrive-synced storage (e.g. %LOCALAPPDATA%\Temp) and in WAL
 * mode — on the OneDrive-synced repo path, concurrent session writes hit "disk I/O error"
 * and every authenticated page 500s. Never run a second process against the DB while the
 * server holds it (that corrupts the file). Then:
 *   VISUAL_QA_PORT=8013 VISUAL_QA_TENANT_PHASE_PORT=8013 TENANT_E2E_SUBDOMAIN=1 \
 *   E2E_TENANT_USER=demo.admin E2E_TENANT_PASSWORD=Test1234 \
 *   VISUAL_QA_TOTP_HEX_KEY=<demo hex> DB_FILE=<db> RMC_E2E_EXTERNAL_SERVER=1 \
 *   npx playwright test tests/e2e/cockpit-sticky-slideover.spec.js --project=chromium --workers=1
 *
 * Validates, on the real authenticated Admin Home, the SHIPPED cockpit fixes:
 *   A. the command/context band (rmc-page-explain-strip) is sticky and STAYS pinned
 *      to the top of the inner scroll column as the dashboard scrolls (cockpit item A)
 *   B. the "Open full activation checklist" CTA opens an rmc-sheet slide-over that
 *      lazy-loads the checklist fragment in place (cockpit item B)
 *   C. journey phases are one-click links, and launch blockers (if any) are direct
 *      resolve links (cockpit item C)
 * plus the earlier shipped fixes (real button, Phase-8 strip retired, appearance
 * picker collapsed).
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

test('A · command band is sticky and stays pinned while the dashboard scrolls', async ({ page }) => {
  await loginTenant(page, { username: 'demo.admin', password: 'Test1234' });
  await gotoAdminHome(page);

  const strip = page.locator('.rmc-page-explain-strip').first();
  await expect(strip).toHaveCount(1);

  // The scoped rule must actually apply.
  expect(await strip.evaluate((el) => getComputedStyle(el).position)).toBe('sticky');

  // Scroll the inner column (the Admin Home scrolls #main-content, not the window) well
  // past the strip's natural height, then confirm the strip is still pinned near the top
  // of that scroll container. A released sticky shows a large negative rel offset
  // (e.g. -220) — the exact regression this proves fixed (rel stays ~0 when pinned).
  const out = await strip.evaluate(async (el) => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    function scrollAncestor(node) {
      let cur = node.parentElement;
      while (cur && cur !== document.body) {
        const cs = getComputedStyle(cur);
        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') &&
            cur.scrollHeight - cur.clientHeight > 20) return cur;
        cur = cur.parentElement;
      }
      return document.scrollingElement || document.documentElement;
    }
    // Wait for layout + the inner column's measured max-height to settle so it is
    // actually scrollable (the dashboard renders progressively).
    let scroller = scrollAncestor(el);
    for (let i = 0; i < 50 && scroller.scrollHeight - scroller.clientHeight < 100; i += 1) {
      await sleep(100);
      scroller = scrollAncestor(el);
    }
    const scTop = () =>
      scroller === document.scrollingElement ? 0 : scroller.getBoundingClientRect().top;
    const target = Math.min(700, scroller.scrollHeight - scroller.clientHeight);
    // Force an instant scroll (guard scroll-behavior:smooth) and confirm it lands
    // before measuring — a same-tick read can catch a mid-animation scrollTop of 0.
    scroller.style.scrollBehavior = 'auto';
    scroller.scrollTop = target;
    for (let i = 0; i < 30 && Math.abs(scroller.scrollTop - target) > 5; i += 1) {
      await sleep(50);
      scroller.scrollTop = target;
    }
    await sleep(100);
    return {
      target,
      scrollTop: scroller.scrollTop,
      rel: el.getBoundingClientRect().top - scTop(),
    };
  });

  expect(out.target).toBeGreaterThan(100);
  expect(out.scrollTop).toBeGreaterThan(100);
  expect(out.rel).toBeGreaterThan(-8);
  expect(out.rel).toBeLessThan(24);
});

test('B · checklist CTA opens a slide-over that loads the checklist in place', async ({ page }) => {
  await loginTenant(page, { username: 'demo.admin', password: 'Test1234' });
  await gotoAdminHome(page);

  const trigger = page.locator("[data-rmc-checklist-drawer='1']").first();
  await expect(trigger).toHaveCount(1);
  // Real button with a real href fallback (no-JS path stays intact).
  const href = await trigger.getAttribute('href');
  expect(href && href.length).toBeTruthy();

  const sheet = page.locator('#rmc-activation-checklist-sheet');
  await expect(sheet).toHaveCount(1);

  // Wait for the fragment endpoint response the click triggers, so the assertion
  // does not race the async fetch.
  const [fragmentResp] = await Promise.all([
    page
      .waitForResponse(
        (r) => /\/onboarding\/fragment\//.test(r.url()) && r.request().method() === 'GET',
        { timeout: 30000 },
      )
      .catch(() => null),
    trigger.click(),
  ]);
  await expect(sheet).toHaveJSProperty('open', true);
  if (fragmentResp) expect(fragmentResp.status()).toBe(200);

  // The loading placeholder is replaced by real content (innerHTML swap removes it),
  // and the drawer shows either real checklist steps or the honest empty state.
  const body = sheet.locator("[data-rmc-checklist-body='1']");
  await expect(body.locator("[data-rmc-checklist-loading='1']")).toHaveCount(0, {
    timeout: 30000,
  });
  await expect(body).toContainText(/complete|checklist will appear here|Start|Review/i, {
    timeout: 30000,
  });

  // Focus is trapped inside the dialog (native <dialog> modal).
  const focusInside = await page.evaluate(() => {
    const dlg = document.getElementById('rmc-activation-checklist-sheet');
    return !!(dlg && document.activeElement && dlg.contains(document.activeElement));
  });
  expect(focusInside).toBe(true);

  // The close affordance closes it.
  await sheet.locator('[data-rmc-sheet-close]').first().click();
  await expect(sheet).toHaveJSProperty('open', false);
});

test('C · journey phases are one-click links; blockers are direct resolve links', async ({ page }) => {
  await loginTenant(page, { username: 'demo.admin', password: 'Test1234' });
  await gotoAdminHome(page);

  const train = page.locator("[data-rmc-readiness-train='1']").first();
  await expect(train).toHaveCount(1);

  // Every journey phase that can be advanced is a one-click link.
  const phaseLinks = train.locator("[data-rmc-phase-link='1']");
  expect(await phaseLinks.count()).toBeGreaterThan(0);
  const firstPhaseHref = await phaseLinks.first().getAttribute('href');
  expect(firstPhaseHref && firstPhaseHref.length).toBeTruthy();

  // If the tenant has launch blockers, each is a direct resolve link (not dead text).
  const blockers = train.locator('.rmc-readiness-train__blocker');
  const blockerCount = await blockers.count();
  if (blockerCount > 0) {
    const bhref = await blockers.first().getAttribute('href');
    expect(bhref && bhref.length && bhref !== '#').toBeTruthy();
  }
});

test('regression · checklist CTA is a real button; Phase-8 strip retired; appearance collapsed', async ({ page }) => {
  await loginTenant(page, { username: 'demo.admin', password: 'Test1234' });
  await gotoAdminHome(page);

  const btn = page.locator('a.rmc-setup-surface__all').first();
  await expect(btn).toHaveCount(1);
  const style = await btn.evaluate((el) => {
    const cs = getComputedStyle(el);
    return {
      display: cs.display,
      padTop: parseFloat(cs.paddingTop),
      borderTop: parseFloat(cs.borderTopWidth),
      height: el.getBoundingClientRect().height,
    };
  });
  expect(style.display).toContain('flex');
  expect(style.padTop).toBeGreaterThan(4);
  expect(style.borderTop).toBeGreaterThan(0);
  expect(style.height).toBeGreaterThan(28);
  await expect(btn.locator('i.bi-check2-square')).toHaveCount(1);

  const strip = page.locator('.phase8-declaration-strip').first();
  await expect(strip).toHaveCount(1);
  const info = await strip.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { w: r.width, h: r.height };
  });
  expect(info.h).toBeLessThanOrEqual(2);
  expect(info.w).toBeLessThanOrEqual(2);

  const disclosure = page.locator('details.rmc-setup-style-strip__disclosure').first();
  if ((await disclosure.count()) > 0) {
    expect(await disclosure.evaluate((el) => el.hasAttribute('open'))).toBe(false);
  }
});
