// @ts-check
/**
 * Marketing visual-quality gate — DOM truth beyond route smoke tests.
 * Requires: MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8010
 */
const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8010';

test.use({ baseURL: MARKETING_BASE_URL });

const CORE_PAGES = [
  { path: '/', name: 'home', marker: '[data-mkt-personality="home"]' },
  { path: '/pricing/', name: 'pricing', marker: '.mkt-v3-pricing-plans__grid, .mkt-v3-page' },
  { path: '/demo/', name: 'demo', marker: '.mkt-v3-form-block' },
  { path: '/contact/', name: 'contact', marker: '.mkt-v3-form-block, #contact-form-block' },
  { path: '/trust/', name: 'trust', marker: '[data-mkt-trust-center]' },
  { path: '/platform/', name: 'platform-hub', marker: '.mkt-v3-page, .mkt-edt-container' },
  { path: '/platform/admissions/', name: 'platform-admissions', marker: '[data-mkt-platform-admissions], .mkt-admissions-page' },
  { path: '/platform/workflows/', name: 'platform-workflows', marker: '[data-mkt-archetype]' },
  { path: '/solutions/international-schools/', name: 'solution-intl', marker: '.mkt-institution-premium' },
  { path: '/resources/', name: 'resources', marker: '.mkt-v3-page--resources' },
];

async function assertNoWideOverflow(page) {
  const delta = await page.evaluate(() => {
    const el = document.documentElement;
    return Math.max(0, el.scrollWidth - el.clientWidth);
  });
  expect.soft(delta, `overflow px=${delta}`).toBeLessThanOrEqual(16);
}

test.describe('marketing visual quality', () => {
  test('enterprise nav has no verb bridge chip', async ({ page }) => {
    await page.goto('/');
    const bridge = page.locator('.mkt-nav-bridge');
    await expect(bridge).toHaveCount(0);
    const labels = await page.locator('.mkt-nav-primary .nav-link').allTextContents();
    const joined = labels.join(' ');
    expect(joined).not.toMatch(/was:\s*Platform/i);
    expect(joined).toMatch(/Platform/);
  });

  test('home walkthrough has no empty video source', async ({ page }) => {
    await page.goto('/');
    const emptySources = await page.locator('source[src=""]').count();
    expect(emptySources).toBe(0);
    const opacity = await page.locator('.reel-scene--2').evaluate((el) => getComputedStyle(el).opacity);
    expect(Number(opacity)).toBeLessThanOrEqual(0.05);
  });

  test('home OS story visuals load', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('[data-mkt-home-journey-visual]')).toBeVisible();
    await expect(page.locator('[data-mkt-home-surfaces-visual]')).toBeVisible();
    const cta = page.locator('[data-mkt-section="os-story"] [data-cta="demo"]').first();
    await expect(cta).toBeVisible();
  });

  test('platform workflows URL resolves after redirect', async ({ page }) => {
    await page.goto('/platform/workflows/');
    expect(page.url()).toMatch(/workflows\/?$/);
    await expect(page.locator('[data-mkt-archetype], .mkt-v3-page, main').first()).toBeVisible();
  });

  for (const spec of CORE_PAGES) {
    test(`${spec.name} — overflow, marker, primary CTA`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 });
      await page.goto(spec.path);
      await assertNoWideOverflow(page);
      await expect(page.locator(spec.marker).first()).toBeVisible();
      if (spec.path === '/pricing/') {
        await expect(page.locator('.mkt-v3-pricing-plans__grid, .mkt-edt-plan').first()).toBeVisible();
      }
      const navCta = page.locator('header [data-cta="demo"]').first();
      await expect(navCta).toBeVisible();
    });
  }
});
