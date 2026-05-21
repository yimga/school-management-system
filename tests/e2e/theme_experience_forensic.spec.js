// @ts-check
/** Forensic master prompt §1d — theme experience hub + builder E2E smoke. */
const { test, expect } = require('@playwright/test');
const { loginManager, MANAGER_BASE_URL } = require('./helpers/manager-login');

const BASE = process.env.MANAGER_BASE_URL || MANAGER_BASE_URL;

test.describe('Theme experience forensic', () => {
  test.beforeEach(async ({ page }) => {
    await loginManager(page);
  });

  test('hub exposes builder hero and light/dark preview', async ({ page }) => {
    await page.goto(`${BASE}/siteconfig/theme-experience/hub/`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('[data-rmc-theme-hub-hero]')).toBeVisible();
    await expect(page.getByRole('link', { name: /open theme builder/i })).toBeVisible();
    const darkBtn = page.locator('.preview-surface-btn[data-preview-surface="dark"]').first();
    await darkBtn.click();
    await expect(page.locator('.theme-hub-mini-preview[data-preview-surface="dark"]')).toBeVisible();
  });

  test('theme builder canvas loads sections and publish controls', async ({ page }) => {
    await page.goto(`${BASE}/siteconfig/theme-experience/builder/`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('#theme-builder-canvas')).toBeVisible();
    await expect(page.locator('#theme-builder-publish')).toBeVisible();
    await expect(page.locator('#theme-builder-preview')).toBeVisible();
    await expect(page.locator('#theme-builder-block-list li').first()).toBeVisible({
      timeout: 20000,
    });
  });
});
