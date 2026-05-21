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
  { path: '/solutions/', name: 'solutions-hub', marker: '[data-mkt-buyer-world-hub]' },
  { path: '/platform/admissions/', name: 'platform-admissions', marker: '[data-mkt-platform-admissions], .mkt-admissions-page' },
  { path: '/platform/student-information-system/', name: 'platform-sis', marker: '[data-mkt-archetype]' },
  { path: '/platform/attendance/', name: 'platform-attendance', marker: '[data-mkt-archetype]' },
  { path: '/platform/fees-payments/', name: 'platform-fees', marker: '[data-mkt-archetype]' },
  { path: '/platform/grading-report-cards/', name: 'platform-grading', marker: '[data-mkt-archetype]' },
  { path: '/platform/parent-portal/', name: 'platform-parent', marker: '[data-mkt-archetype]' },
  { path: '/platform/teacher-portal/', name: 'platform-teacher', marker: '[data-mkt-archetype]' },
  { path: '/platform/student-portal/', name: 'platform-student', marker: '[data-mkt-archetype]' },
  { path: '/platform/communications/', name: 'platform-comms', marker: '[data-mkt-archetype]' },
  { path: '/platform/analytics/', name: 'platform-analytics', marker: '[data-mkt-archetype]' },
  { path: '/platform/workflows/', name: 'platform-workflows', marker: '[data-mkt-archetype]' },
  { path: '/platform/offline-first/', name: 'platform-offline', marker: '[data-mkt-archetype]' },
  { path: '/platform/security/', name: 'platform-security', marker: '[data-mkt-archetype]' },
  { path: '/solutions/private-schools/', name: 'solution-private', marker: '.mkt-institution-premium' },
  { path: '/solutions/international-schools/', name: 'solution-intl', marker: '.mkt-institution-premium' },
  { path: '/solutions/k12-schools/', name: 'solution-k12', marker: '.mkt-institution-premium' },
  { path: '/solutions/multi-campus/', name: 'solution-multi', marker: '.mkt-institution-premium' },
  { path: '/solutions/faith-based-schools/', name: 'solution-faith', marker: '.mkt-institution-premium' },
  { path: '/solutions/growing-school-networks/', name: 'solution-growing', marker: '.mkt-institution-premium' },
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

  test('mega menus keep distinct buyer-facing jobs', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');

    await page.locator('header [data-menu-name="Platform"]').first().click();
    let menu = page.locator('.mkt-mega-menu.show').first();
    await expect(menu).toContainText('Core Operations');
    await expect(menu).toContainText('Role Workspaces');
    await expect(menu).toContainText('Inquiry');
    await page.keyboard.press('Escape');

    await page.locator('header [data-menu-name="Solutions"]').first().click();
    menu = page.locator('.mkt-mega-menu.show').first();
    for (const label of [
      'Private Schools',
      'International Schools',
      'Multi-Campus Groups',
      'Faith-Based Schools',
      'Growing School Networks',
    ]) {
      await expect(menu).toContainText(label);
    }
    await expect(menu).not.toContainText('Finance teams');
    await expect(menu).not.toContainText('Teachers & academics');
    await page.keyboard.press('Escape');

    await page.locator('header [data-menu-name="Why RunMyCampus"]').first().click();
    await expect(page.locator('.mkt-mega-menu.show').first()).toContainText('Trust & procurement');
    await page.keyboard.press('Escape');

    await page.locator('header [data-menu-name="Resources"]').first().click();
    await expect(page.locator('.mkt-mega-menu.show').first()).toContainText('Procurement checklist');
    await page.keyboard.press('Escape');

    await page.locator('header [data-menu-name="More"]').first().click();
    menu = page.locator('.mkt-mega-menu.show').first();
    await expect(menu).toContainText('Company & utility');
    await expect(menu).toContainText('Trust & legal');
    await expect(menu).not.toContainText('Attendance');
  });

  test('home walkthrough has no empty video source', async ({ page }) => {
    await page.goto('/');
    const emptySources = await page.locator('source[src=""]').count();
    expect(emptySources).toBe(0);
    await expect(page.locator('[data-mkt-walkthrough-play]')).toHaveCount(0);
    await expect(page.getByLabel(/open the product walkthrough/i)).toBeVisible();
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

  test('solutions hub stays buyer-world specific', async ({ page }) => {
    await page.goto('/solutions/');
    await expect(page.locator('[data-mkt-buyer-world-hub]')).toBeVisible();
    await expect(page.locator('[data-mkt-buyer-world]')).toHaveCount(6);
    await expect(page.locator('[data-mkt-persona-tabs]')).toHaveCount(0);
    await expect(page.getByText('Finance teams', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Teachers & academics', { exact: true })).toHaveCount(0);
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
      await expect(page.locator('a[href="#"], button[href="#"]')).toHaveCount(0);
    });
  }

  test('mobile nav opens without horizontal overflow or clipped primary CTA', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.getByRole('button', { name: /toggle navigation/i }).click();
    await expect(page.locator('#marketingNav')).toBeVisible();
    await expect(page.locator('header [data-cta="demo"]').first()).toBeVisible();
    await assertNoWideOverflow(page);
  });
});
