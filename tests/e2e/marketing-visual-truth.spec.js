// @ts-check
/**
 * Marketing visual-truth regression (overflow, hero, v3 pages, verb hubs).
 * Requires Django: MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8010
 */
const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8010';

test.use({ baseURL: MARKETING_BASE_URL });

let AxeBuilder = null;
try {
  AxeBuilder = require('@axe-core/playwright').default;
} catch (_) {
  /* optional */
}

const SKIP_AXE = process.env.SKIP_AXE === '1';

const VIEWPORTS = [
  { width: 375, height: 812, label: 'mobile' },
  { width: 1280, height: 720, label: 'desktop' },
];

const PAGES = [
  { path: '/', hero: '.mkt-edt-hero__artifact, .mkt-v3-dashboard-frame', name: 'home' },
  { path: '/pricing/', hero: '.mkt-v3-pricing-plans__grid, .mkt-v3-page', name: 'pricing' },
  { path: '/why-switch/', hero: '.mkt-v3-competitor-matrix', name: 'why-switch' },
  { path: '/contact/', hero: '.mkt-v3-form-block, #contact-form-block', name: 'contact' },
  { path: '/demo/', hero: '.mkt-v3-form-block', name: 'demo' },
  { path: '/company/', hero: '.mkt-v3-page--company, .mkt-v3-segment-card', name: 'company' },
  { path: '/resources/', hero: '.mkt-v3-page--resources', name: 'resources' },
  { path: '/developers/', hero: '.mkt-v3-page--developers', name: 'developers' },
  { path: '/solutions/head/', hero: '.mkt-v3-page--persona', name: 'solutions-head' },
  { path: '/run/', hero: '.mkt-v3-page, .mkt-edt-container', name: 'run-hub' },
  { path: '/teach/', hero: '.mkt-v3-page, .mkt-edt-container', name: 'teach-hub' },
  { path: '/pay/', hero: '.mkt-v3-page, .mkt-edt-container', name: 'pay-hub' },
  { path: '/communicate/', hero: '.mkt-v3-page, .mkt-edt-container', name: 'communicate-hub' },
  { path: '/grow/', hero: '.mkt-v3-page, .mkt-edt-container', name: 'grow-hub' },
  { path: '/platform/integrations/', hero: '.mkt-v3-archetype', name: 'platform-integrations' },
];

async function assertNoWideOverflow(page) {
  const delta = await page.evaluate(() => {
    const el = document.documentElement;
    return Math.max(0, el.scrollWidth - el.clientWidth);
  });
  expect.soft(delta, `overflow px=${delta}`).toBeLessThanOrEqual(16);
}

async function scanAxe(page, label) {
  if (SKIP_AXE || !AxeBuilder) return;
  const results = await new AxeBuilder({ page }).analyze();
  expect.soft(results.violations, `axe violations on ${label}`).toEqual([]);
}

test.describe('marketing visual truth', () => {
  test('home walkthrough reel hides non-first scenes initially', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    const opacity = await page.locator('.reel-scene--2').evaluate((el) => getComputedStyle(el).opacity);
    expect(Number(opacity)).toBeLessThanOrEqual(0.01);
    await assertNoWideOverflow(page);
    const heroVisible = await page.locator('.mkt-edt-hero__artifact, .mkt-v3-dashboard-frame').first().isVisible();
    expect(heroVisible).toBeTruthy();
    const cta = page.locator('.mkt-edt-hero__ctas a, .mkt-edt-cta').first();
    await expect(cta).toBeVisible();
    const footerSize = await page.locator('footer, .mkt-footer').first().evaluate((el) => {
      const target = el.querySelector('a, p, span') || el;
      return parseFloat(getComputedStyle(target).fontSize);
    });
    expect(footerSize).toBeGreaterThanOrEqual(14);
    await scanAxe(page, '/');
  });

  test('home pricing teaser avoids exact pound figures', async ({ page }) => {
    await page.goto('/');
    const body = await page.locator('#mkt-edt-root, main').first().innerText();
    expect(body).not.toMatch(/£3(?![\d,])/);
    expect(body).not.toMatch(/£6(?![\d,])/);
  });

  for (const vp of VIEWPORTS) {
    for (const spec of PAGES) {
      test(`${spec.name} @ ${vp.label} — no overflow + hero`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await page.goto(spec.path);
        await assertNoWideOverflow(page);
        await expect(page.locator(spec.hero).first()).toBeVisible();
        if (vp.label === 'desktop' && spec.path === '/why-switch/') {
          await expect(page.locator('.mkt-v3-comparison-matrix')).toBeVisible();
        }
        if (vp.label === 'desktop' && spec.path === '/pricing/') {
          await expect(page.locator('[data-mkt-currency-switcher]')).toBeVisible();
        }
        await scanAxe(page, `${spec.path}@${vp.label}`);
      });
    }
  }
});
