// @ts-check
/**
 * Dual-plane theme & experience — manager (platform) vs tenant (school) hosts.
 *
 * CI: bash scripts/run_theme_experience_dual_plane_e2e.sh
 * Local: npm run test:e2e:theme-dual-plane:lane2
 */
const { test, expect } = require('@playwright/test');
const { loginManager, MANAGER_BASE_URL } = require('./helpers/manager-login');
const { appleClassLogin } = require('./helpers/apple-class-login');

const MANAGER_BASE =
  process.env.MANAGER_BASE_URL || MANAGER_BASE_URL;
const TENANT_HOST =
  process.env.TENANT_E2E_HOST || 'apple-class-qa.runmycampus.com';
const TENANT_PORT = process.env.VISUAL_QA_PORT || '8014';
const TENANT_BASE =
  process.env.TENANT_BASE_URL || `http://${TENANT_HOST}:${TENANT_PORT}`;
const TENANT_USER =
  process.env.E2E_USERNAME ||
  process.env.APPLE_QA_TENANT_USERNAME ||
  'appleqa_tenant';
const TENANT_PASS =
  process.env.E2E_PASSWORD ||
  process.env.APPLE_QA_TENANT_PASSWORD ||
  'AppleQaPass123!';

const PUBLISH_API = '/siteconfig/theme-experience/builder/api/publish/';
const ROLLBACK_API = '/siteconfig/theme-experience/builder/api/rollback/';

/** Same-origin fetch from the active host (Playwright API context ignores host-resolver-rules). */
async function postJson(page, path, data) {
  return page.evaluate(async ({ path, payload }) => {
    const csrf =
      document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ||
      document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
      '';
    const resp = await fetch(path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload ?? {}),
    });
    const text = await resp.text();
    let json = {};
    try {
      json = JSON.parse(text);
    } catch (_e) {
      json = { raw: text };
    }
    return { ok: resp.ok, status: resp.status, json, text };
  }, { path, payload: data });
}

test.describe.configure({ timeout: 120000 });

test.describe('Theme experience — manager plane', () => {
  test.beforeEach(async ({ page }) => {
    await loginManager(page);
  });

  test('hub shows platform operator plane, glance, and builder CTA', async ({ page }) => {
    await page.goto(`${MANAGER_BASE}/siteconfig/theme-experience/hub/`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('[data-rmc-plane="platform"]')).toBeVisible();
    await expect(page.locator('.badge.text-bg-primary')).toContainText(/platform operator/i);
    await expect(page.locator('.rmc-cp-compact__fold-nav')).toBeVisible();
    await expect(page.locator('#theme-hub-glance')).toBeVisible();
    await expect(page.locator('.rmc-theme-hub-contrast-pill')).toBeVisible();
    await expect(page.getByRole('link', { name: /open theme builder/i })).toBeVisible();
  });

  test('builder uses platform plane chrome and publish history', async ({ page }) => {
    await page.goto(`${MANAGER_BASE}/siteconfig/theme-experience/builder/`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('[data-rmc-plane="platform"]')).toBeVisible();
    await expect(page.locator('#theme-builder-canvas')).toBeVisible();
    await expect(page.locator('#theme-builder-rollback')).toBeVisible();
    await expect(page.locator('#theme-builder-publish-log')).toBeVisible();
    await expect(page.locator('#theme-builder-block-list li').first()).toBeVisible({
      timeout: 20000,
    });
  });

  test('rollback restores previous publish on platform plane', async ({ page }) => {
    await page.goto(`${MANAGER_BASE}/siteconfig/theme-experience/builder/`, {
      waitUntil: 'domcontentloaded',
    });
    const layoutLight = {
      surface: 'light',
      blocks: [{ id: 'hero', type: 'hero', label: 'Hero', enabled: true }],
    };
    const layoutDark = {
      surface: 'dark',
      blocks: [{ id: 'hero', type: 'hero', label: 'Hero', enabled: true }],
    };
    const colors = { primary_color: '#112233', accent_color: '#445566' };

    for (const layout of [layoutLight, layoutDark]) {
      const resp = await postJson(page, PUBLISH_API, {
        layout,
        colors,
        publish: true,
        preview_confirmed: true,
      });
      expect(resp.ok, `publish failed: ${resp.status} ${resp.text}`).toBeTruthy();
    }

    const rollback = await postJson(page, ROLLBACK_API, {});
    expect(rollback.ok, `rollback failed: ${rollback.status} ${rollback.text}`).toBeTruthy();
    expect(rollback.json.ok, JSON.stringify(rollback.json)).toBeTruthy();
    expect(rollback.json.layout?.surface).toBe('light');
  });
});

test.describe('Theme experience — tenant plane', () => {
  test.beforeEach(async ({ page }) => {
    await appleClassLogin(page, TENANT_BASE, TENANT_USER, TENANT_PASS);
  });

  test('hub shows school tenant plane and does not show platform badge', async ({ page }) => {
    const hubResp = await page.goto(`${TENANT_BASE}/siteconfig/theme-experience/hub/`, {
      waitUntil: 'domcontentloaded',
    });
    expect(hubResp?.status(), await page.locator('body').innerText()).toBeLessThan(400);
    await expect(page.locator('[data-rmc-plane="tenant"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.badge.text-bg-success')).toContainText(/school tenant/i);
    await expect(page.locator('[data-rmc-plane="platform"]')).toHaveCount(0);
    await expect(page.locator('#theme-hub-glance')).toBeVisible();
    await expect(page.locator('.rmc-theme-hub-glance__chip').first()).toBeVisible();
  });

  test('builder shows tenant plane, rollback, and live canvas', async ({ page }) => {
    await page.goto(`${TENANT_BASE}/siteconfig/theme-experience/builder/`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('[data-rmc-plane="tenant"]')).toBeVisible();
    await expect(page.locator('#theme-builder-rollback')).toBeVisible();
    await expect(page.locator('#theme-builder-publish')).toBeVisible();
    await expect(page.locator('#theme-builder-canvas')).toBeVisible();
  });

  test('tenant rollback API restores prior surface', async ({ page }) => {
    await page.goto(`${TENANT_BASE}/siteconfig/theme-experience/builder/`, {
      waitUntil: 'domcontentloaded',
    });
    const layoutLight = {
      surface: 'light',
      blocks: [{ id: 'hero', type: 'hero', label: 'Hero', enabled: true }],
    };
    const layoutDark = {
      surface: 'dark',
      blocks: [{ id: 'hero', type: 'hero', label: 'Hero', enabled: true }],
    };
    const colors = { primary_color: '#112233', accent_color: '#445566' };

    let firstPublish = true;
    for (const layout of [layoutLight, layoutDark]) {
      const payload = {
        layout,
        publish: true,
        preview_confirmed: true,
      };
      if (firstPublish) {
        payload.colors = colors;
        firstPublish = false;
      }
      const resp = await postJson(page, PUBLISH_API, payload);
      expect(resp.ok, `publish failed: ${resp.status} ${resp.text}`).toBeTruthy();
    }

    const rollback = await postJson(page, ROLLBACK_API, {});
    expect(rollback.ok, `rollback failed: ${rollback.status} ${rollback.text}`).toBeTruthy();
    expect(rollback.json.ok, JSON.stringify(rollback.json)).toBeTruthy();
    expect(rollback.json.layout?.surface).toBe('light');
  });
});
