// @ts-check
/**
 * VISUAL-ENGINE-10X smoke: four homepage personalities + regional + platform viz.
 *
 * Local (runmycampus.com host → 127.0.0.1):
 *   MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8000
 *   MARKETING_BASE_URL=http://runmycampus.com:8000 npx playwright test tests/e2e/marketing-visual-engine.spec.js
 *
 * Production:
 *   npm run test:e2e:marketing:visual-engine:production
 */
const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8000';

test.use({ baseURL: MARKETING_BASE_URL });

const PERSONALITY_IDS = [
  'mkt-sovereign-kernel',
  'mkt-clinical-ledger',
  'mkt-rugged-engine',
  'mkt-fluid-classroom',
];

test.describe('marketing visual engine', () => {
  test('/storefront/ One Record Scroll exposes pinned sim stage', async ({ page }) => {
    const res = await page.goto('/storefront/', {
      waitUntil: 'domcontentloaded',
      timeout: 45000,
    });
    expect(res?.status() ?? 500).toBeLessThan(400);
    await expect(page.locator('[data-mkt-one-record-scroll]')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('#panel-run.is-active, #panel-run:not([hidden])').first()).toBeVisible();
    await expect(page.locator('[data-mkt-speed-duel]')).toBeVisible();
    const chapterPay = page.locator('#or-ch-pay');
    await chapterPay.scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await expect(page.locator('#panel-pay.is-active, #panel-pay:not([hidden])').first()).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator('[data-mkt-split-ledger]')).toBeVisible();
  });

  test('homepage exposes four personality sections', async ({ page }) => {
    const res = await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    expect(res?.status() ?? 500).toBeLessThan(400);
    for (const id of PERSONALITY_IDS) {
      await expect(page.locator(`#${id}`)).toBeVisible({ timeout: 15000 });
    }
    await expect(page.locator('[data-mkt-sandbox-form]')).toBeVisible();
    await expect(page.locator('.mkt-ve-loop').first()).toBeVisible();
  });

  test('regional shortcut /ng/ renders personalities', async ({ page }) => {
    const res = await page.goto('/ng/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    expect(res?.status() ?? 500).toBeLessThan(400);
    const sovereign = page.locator('#mkt-sovereign-kernel');
    await sovereign.scrollIntoViewIfNeeded();
    await expect(sovereign).toBeVisible({ timeout: 15000 });
    await expect(page.locator('#mkt-edt-root[data-mkt-edition="editorial"]')).toBeVisible();
    await expect(page.locator('body[data-rmc-country="NG"]')).toBeVisible();
  });

  test('canonical /en/us/ regional route resolves', async ({ page }) => {
    const res = await page.goto('/en/us/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    expect(res?.status() ?? 500).toBeLessThan(400);
    await expect(page.locator('#mkt-clinical-ledger')).toBeVisible({ timeout: 15000 });
  });

  test('platform admissions includes visual engine strip', async ({ page }) => {
    const res = await page.goto('/platform/admissions/', {
      waitUntil: 'domcontentloaded',
      timeout: 45000,
    });
    expect(res?.status() ?? 500).toBeLessThan(400);
    await expect(page.locator('[data-mkt-platform-admissions]')).toBeVisible();
    await expect(page.locator('.mkt-viz, .mkt-ve-platform-loop').first()).toBeVisible({
      timeout: 15000,
    });
  });

  test('split ledger slider updates on clinical personality section', async ({ page }) => {
    const res = await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    expect(res?.status() ?? 500).toBeLessThan(400);
    const clinical = page.locator('#mkt-clinical-ledger');
    await clinical.scrollIntoViewIfNeeded();
    const slider = clinical.locator('[data-mkt-split-slider]');
    await expect(slider).toBeVisible({ timeout: 15000 });
    const before = await page.locator('.mkt-viz--split-ledger rect:nth-of-type(3)').getAttribute('width');
    await slider.fill('40');
    await page.waitForTimeout(200);
    const after = await page.locator('.mkt-viz--split-ledger rect:nth-of-type(3)').getAttribute('width');
    expect(before).not.toEqual(after);
  });
});
