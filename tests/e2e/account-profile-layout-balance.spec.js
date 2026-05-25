// @ts-check
const { test, expect } = require('@playwright/test');
const {
  ensureManagerHost,
  ensureManagerSession,
  AUTH_STATE_PATH,
} = require('./helpers/manager-login');

const MANAGER_HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const MANAGER_PORT = process.env.VISUAL_QA_PORT || '8012';
const MANAGER_BASE_URL =
  process.env.MANAGER_BASE_URL ||
  process.env.BASE_URL ||
  `http://${MANAGER_HOST}:${MANAGER_PORT}`;

const MANAGER_USERNAME = process.env.VISUAL_QA_USERNAME || 'visualqa_admin';
const MANAGER_PASSWORD = process.env.VISUAL_QA_PASSWORD || 'VisualQaPass123!';

async function waitForProfileContract(page, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if ((await page.locator('[data-rmc-balanced-profile="1"]').count()) > 0) {
      return true;
    }
    await page.waitForTimeout(1500);
  }
  return false;
}

test.use({
  baseURL: MANAGER_BASE_URL,
  storageState: AUTH_STATE_PATH,
  viewport: { width: 1600, height: 1000 },
});

test.describe('account profile layout balance', () => {
  test('manager profile balances security content and action rail', async ({ page }) => {
    await page.goto('/authentication/profile/#profile-security-strength', {
      waitUntil: 'commit',
      timeout: 60000,
    });
    const cdp = await page.context().newCDPSession(page);
    let profileReady = await waitForProfileContract(page);
    if (!profileReady) {
      await ensureManagerSession(page, {
        username: MANAGER_USERNAME,
        password: MANAGER_PASSWORD,
      });
      await page.evaluate(() => {
        window.location.assign('/authentication/profile/#profile-security-strength');
      });
      profileReady = await waitForProfileContract(page);
    }
    expect(profileReady).toBe(true);
    await page.keyboard.press('Escape').catch(() => {});
    await cdp.send('Page.stopLoading').catch(() => {});

    const metrics = await page.evaluate(() => {
      const shell = document.querySelector('[data-rmc-balanced-profile="1"]');
      const grid = document.querySelector('[data-rmc-balanced-layout="account-profile"]');
      const primary = document.querySelector('.rmc-account-layout-grid__primary');
      const rail = document.querySelector('.rmc-account-layout-grid__rail');
      const sidebarLabels = Array.from(
        document.querySelectorAll('#cpSidebarNav > .cp-sidebar__group > summary')
      )
        .map((el) => (el.textContent || '').trim().toLowerCase())
        .filter(Boolean);
      const duplicates = sidebarLabels.filter(
        (label, index) => sidebarLabels.indexOf(label) !== index
      );
      const gridStyle = grid ? getComputedStyle(grid) : null;
      const railCards = rail
        ? rail.querySelectorAll('.card, .content-card, .rmc-profile-security-hub').length
        : 0;
      const primaryHeight = primary ? primary.getBoundingClientRect().height : 0;
      const railHeight = rail ? rail.getBoundingClientRect().height : 0;
      const gridWidth = grid ? grid.getBoundingClientRect().width : 0;
      return {
        markerVisible: !!(shell && shell.getBoundingClientRect().height > 0),
        columnCount: gridStyle
          ? gridStyle.gridTemplateColumns.split(' ').filter(Boolean).length
          : 0,
        railCards,
        primaryHeight,
        railHeight,
        gridWidth,
        docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        duplicateSidebarLabels: Array.from(new Set(duplicates)),
      };
    });

    expect(metrics.markerVisible).toBe(true);
    expect(metrics.columnCount).toBeGreaterThanOrEqual(2);
    expect(metrics.gridWidth).toBeGreaterThan(1000);
    expect(metrics.railCards).toBeGreaterThanOrEqual(3);
    expect(metrics.primaryHeight).toBeGreaterThan(300);
    expect(metrics.railHeight / Math.max(metrics.primaryHeight, 1)).toBeGreaterThan(0.45);
    expect(metrics.docOverflow).toBeLessThanOrEqual(24);
    expect(metrics.duplicateSidebarLabels).toEqual([]);
  });
});
