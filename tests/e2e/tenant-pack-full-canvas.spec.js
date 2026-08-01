// @ts-check
/**
 * Real-host visual/DOM certification for the approved Tenant Pack full canvas.
 * Chromium resolves demo-school.runmycampus.com to the local Django server;
 * loginTenant completes the real password + MFA flow against the tenant host.
 */
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { loginTenant, TENANT_BASE_URL } = require('./helpers/tenant-login');

const ROOT = path.join(__dirname, '..', '..');
const EVIDENCE_DIR = path.join(
  ROOT,
  'artifacts',
  'design-approvals',
  'tenant-pack-full-canvas-implementation-2026-07-31',
);
const ROUTE = `${TENANT_BASE_URL}/school/setup/packs/`;
const VIEWPORTS = [
  { name: '1440', width: 1440, height: 1000 },
  { name: '1024', width: 1024, height: 900 },
  { name: '768', width: 768, height: 900 },
  { name: '390', width: 390, height: 844 },
];

test.describe('Tenant Pack approved full-canvas implementation', () => {
  test.setTimeout(600000);
  test.beforeAll(() => fs.mkdirSync(EVIDENCE_DIR, { recursive: true }));

  test('real tenant host, responsive themes, resources, DOM, and genuine actions', async ({ page }) => {
    const consoleErrors = [];
    const brokenResources = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('response', (response) => {
      const url = response.url();
      if (response.status() >= 400 && /\.(?:css|js|png|jpe?g|svg|woff2?)(?:\?|$)/i.test(url)) {
        brokenResources.push({ status: response.status(), url });
      }
    });

    await loginTenant(page, {
      username: process.env.E2E_TENANT_USER || 'demo.admin',
    });

    const evidence = [];
    for (const theme of ['dark', 'light']) {
      for (const viewport of VIEWPORTS) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        const response = await page.goto(ROUTE, {
          waitUntil: 'domcontentloaded',
          timeout: 120000,
        });
        expect(response, `${theme}/${viewport.name} navigation response`).not.toBeNull();
        expect(response.status(), `${theme}/${viewport.name} HTTP status`).toBe(200);
        expect(new URL(page.url()).hostname).toBe('demo-school.runmycampus.com');

        await page.evaluate((activeTheme) => {
          document.documentElement.setAttribute('data-theme', activeTheme);
          document.documentElement.setAttribute('data-bs-theme', activeTheme);
          document.documentElement.setAttribute('data-cockpit-skin', activeTheme);
        }, theme);
        await page.waitForTimeout(250);

        const main = page.locator('[data-rmc-tenant-pack-workbench="1"]');
        await expect(main).toBeVisible();
        await expect(page.locator('h1:visible')).toHaveCount(1);
        await expect(main.locator('[data-rmc-operational-center-frame="1"]')).toHaveCount(1);
        await expect(main.locator('[data-rmc-pack-inspector="1"]')).toBeVisible();
        await expect(main.locator('form[data-rmc-genuine-pack-action="1"]')).toHaveCount(1);
        await expect(main.locator('form[data-rmc-genuine-pack-action="1"] input[name="csrfmiddlewaretoken"]')).toHaveCount(1);

        const dom = await page.evaluate(() => {
          const root = document.documentElement;
          const mainNode = document.querySelector('[data-rmc-tenant-pack-workbench="1"]');
          const layout = document.querySelector('.rmc-tpw-layout');
          const cssUrls = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
            .map((node) => node.href);
          const rawIconPattern = /^(?:chevron_(?:left|right|up|down)|more_vert|menu_open|close|settings)$/i;
          const rawIconNames = Array.from(document.querySelectorAll('body *'))
            .filter((node) => {
              const style = getComputedStyle(node);
              const text = (node.textContent || '').trim();
              return style.display !== 'none' && style.visibility !== 'hidden' && rawIconPattern.test(text);
            })
            .map((node) => (node.textContent || '').trim());
          const fixedInsideMain = mainNode
            ? Array.from(mainNode.querySelectorAll('*')).filter((node) => getComputedStyle(node).position === 'fixed').length
            : -1;
          const mainRect = mainNode ? mainNode.getBoundingClientRect() : null;
          return {
            clientWidth: root.clientWidth,
            scrollWidth: root.scrollWidth,
            h1Visible: Array.from(document.querySelectorAll('h1')).filter((node) => {
              const rect = node.getBoundingClientRect();
              const style = getComputedStyle(node);
              return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }).length,
            mainWidth: mainRect ? mainRect.width : 0,
            layoutColumns: layout ? getComputedStyle(layout).gridTemplateColumns : '',
            cssCount: cssUrls.length,
            duplicateCssUrls: cssUrls.filter((url, index) => cssUrls.indexOf(url) !== index),
            stylesheetLinksInBody: document.body.querySelectorAll('link[rel="stylesheet"]').length,
            fixedInsideMain,
            rawIconNames,
            operatorLeakage: /\b(?:Studio OS|fleet controls|global registries|Invite School)\b/i.test(mainNode?.innerText || ''),
            postForms: mainNode ? Array.from(mainNode.querySelectorAll('form[method="post"]')).length : 0,
            nativeTableDisplay: (() => {
              const table = mainNode?.querySelector('table.rmc-tpw-table');
              return table ? getComputedStyle(table).display : 'not-rendered';
            })(),
          };
        });

        expect(dom.h1Visible).toBe(1);
        expect(dom.scrollWidth).toBeLessThanOrEqual(dom.clientWidth + 1);
        expect(dom.mainWidth).toBeGreaterThan(viewport.width * 0.72);
        expect(dom.duplicateCssUrls).toEqual([]);
        expect(dom.stylesheetLinksInBody).toBe(0);
        expect(dom.fixedInsideMain).toBe(0);
        expect(dom.rawIconNames).toEqual([]);
        expect(dom.operatorLeakage).toBe(false);
        expect(dom.postForms).toBeGreaterThan(0);
        if (viewport.width <= 1024) {
          expect(dom.layoutColumns.trim().split(/\s+/)).toHaveLength(1);
        } else {
          expect(dom.layoutColumns.trim().split(/\s+/).length).toBeGreaterThanOrEqual(2);
        }

        const shot = path.join(EVIDENCE_DIR, `tenant-pack-${theme}-${viewport.name}.png`);
        await page.screenshot({ path: shot, fullPage: true });
        evidence.push({ theme, viewport, url: page.url(), status: response.status(), ...dom, screenshot: path.relative(ROOT, shot).replace(/\\/g, '/') });
      }
    }

    const simulated = await page.goto(
      `${ROUTE}?pack=attendance-recovery&pack_type=workflow_pack&simulate=1`,
      { waitUntil: 'domcontentloaded', timeout: 120000 },
    );
    expect(simulated).not.toBeNull();
    expect(simulated.status()).toBe(200);
    await expect(page.locator('[data-rmc-real-simulation="1"]')).toBeVisible();

    const filtered = await page.goto(
      `${ROUTE}?q=attendance+recovery&catalog_type=workflow_pack`,
      { waitUntil: 'domcontentloaded', timeout: 120000 },
    );
    expect(filtered).not.toBeNull();
    expect(filtered.status()).toBe(200);
    await expect(page.locator('[data-world-class-tenant-card="1"]')).toHaveCount(1);
    await expect(page.getByRole('heading', { name: 'Attendance Recovery', exact: true }).first()).toBeVisible();

    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'tenant-pack-full-canvas-browser-evidence.json'),
      `${JSON.stringify({ generatedAt: new Date().toISOString(), evidence, consoleErrors, brokenResources }, null, 2)}\n`,
      'utf8',
    );
    expect(brokenResources).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
