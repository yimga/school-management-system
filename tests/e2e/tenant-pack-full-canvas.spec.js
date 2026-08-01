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
const HEAD_OWNERSHIP_ROUTES = [
  { slug: 'studio-experience', path: '/studio/experience/' },
];
const VIEWPORTS = process.env.RMC_TENANT_PACK_QUICK === '1' ? [
  { name: '1440', width: 1440, height: 1000 },
] : [
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
    const environmentWarnings = [];
    const brokenResources = [];
    const httpFailures = [];
    page.on('console', (message) => {
      if (message.type() !== 'error') return;
      const value = message.text();
      // The evidence server intentionally uses plain HTTP + Django's WSGI
      // runserver. Production is HTTPS + ASGI, so these two diagnostics are
      // local transport limitations rather than application failures.
      if (
        value.includes('Cross-Origin-Opener-Policy header has been ignored')
        || value.includes("WebSocket connection to 'ws://demo-school.runmycampus.com:8013/ws/notifications/' failed")
        || (
          value.includes("Framing 'https://demo-school.runmycampus.com/'")
          && value.includes("default-src 'self'")
          && TENANT_BASE_URL.startsWith('http://')
        )
      ) {
        environmentWarnings.push(value);
        return;
      }
      consoleErrors.push(value);
    });
    page.on('response', (response) => {
      const url = response.url();
      if (response.status() >= 400) {
        if (response.status() === 404 && /\/ws\/notifications\/$/.test(new URL(url).pathname)) {
          environmentWarnings.push(`HTTP ${response.status()} ${url} (local WSGI websocket probe)`);
        } else {
          httpFailures.push({ status: response.status(), method: response.request().method(), url });
        }
      }
      if (response.status() >= 400 && /\.(?:css|js|png|jpe?g|svg|woff2?)(?:\?|$)/i.test(url)) {
        brokenResources.push({ status: response.status(), url });
      }
    });

    if (process.env.PLAYWRIGHT_TENANT_STORAGE_STATE) {
      // Authentication comes from the explicitly supplied iterative state.
    } else {
      await loginTenant(page, {
        username: process.env.E2E_TENANT_USER || 'demo.admin',
      });
      await page.context().storageState({ path: path.join(EVIDENCE_DIR, 'tenant-pack-auth-state.json') });
    }

    const certifiedResponse = await page.goto(ROUTE, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    expect(certifiedResponse).not.toBeNull();
    expect(certifiedResponse.status()).toBe(200);
    expect(new URL(page.url()).hostname).toBe('demo-school.runmycampus.com');

    const evidence = [];
    for (const theme of ['dark', 'light']) {
      for (const viewport of VIEWPORTS) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        expect(new URL(page.url()).hostname).toBe('demo-school.runmycampus.com');

        await page.evaluate((activeTheme) => {
          if (!window.RMCTheme || typeof window.RMCTheme.set !== 'function') {
            throw new Error('RMCTheme API unavailable');
          }
          window.RMCTheme.set(activeTheme);
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
          const canvasNode = mainNode?.closest('[data-rmc-django-surface-canvas]');
          const pageWrap = mainNode?.closest('.page-wrap');
          const layout = document.querySelector('.rmc-tpw-layout');
          const desktopSidebar = document.querySelector('[data-shell-sidebar-mount="desktop"]');
          const mobileSidebar = document.querySelector('[data-shell-sidebar-mount="offcanvas"]');
          const cssUrls = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
            .map((node) => node.href);
          const rawIconPattern = /^(?:chevron_(?:left|right|up|down)|more_vert|menu_open|close|settings)$/i;
          const rawIconNames = Array.from(document.querySelectorAll('body *'))
            .filter((node) => {
              const style = getComputedStyle(node);
              const text = (node.textContent || '').trim();
              const isIconNode = node.matches(
                '.material-icons, .material-icons-outlined, .material-symbols-outlined, .material-symbols-rounded, [data-rmc-icon-font]',
              ) || /material (?:icons|symbols)/i.test(style.fontFamily || '');
              return isIconNode && style.display !== 'none' && style.visibility !== 'hidden' && rawIconPattern.test(text);
            })
            .map((node) => (node.textContent || '').trim());
          const fixedInsideMain = mainNode
            ? Array.from(mainNode.querySelectorAll('*')).filter((node) => getComputedStyle(node).position === 'fixed').length
            : -1;
          const mainRect = mainNode ? mainNode.getBoundingClientRect() : null;
          const canvasRect = canvasNode ? canvasNode.getBoundingClientRect() : null;
          const pageWrapRect = pageWrap ? pageWrap.getBoundingClientRect() : null;
          return {
            clientWidth: root.clientWidth,
            scrollWidth: root.scrollWidth,
            h1Visible: Array.from(document.querySelectorAll('h1')).filter((node) => {
              const rect = node.getBoundingClientRect();
              const style = getComputedStyle(node);
              return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }).length,
            mainWidth: mainRect ? mainRect.width : 0,
            canvasWidth: canvasRect ? canvasRect.width : 0,
            pageWrapWidth: pageWrapRect ? pageWrapRect.width : 0,
            layoutColumns: layout ? getComputedStyle(layout).gridTemplateColumns : '',
            resolvedTheme: root.getAttribute('data-resolved-theme'),
            desktopSidebarDisplay: desktopSidebar ? getComputedStyle(desktopSidebar).display : 'missing',
            mobileSidebarOpen: mobileSidebar ? mobileSidebar.classList.contains('show') : false,
            cssCount: cssUrls.length,
            duplicateCssUrls: cssUrls.filter((url, index) => cssUrls.indexOf(url) !== index),
            bodyStylesheetUrls: Array.from(document.body.querySelectorAll('link[rel="stylesheet"]')).map((node) => node.href),
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

        const shot = path.join(EVIDENCE_DIR, `tenant-pack-${theme}-${viewport.name}.png`);
        await page.screenshot({ path: shot, fullPage: true });
        evidence.push({ theme, viewport, url: page.url(), status: certifiedResponse.status(), ...dom, screenshot: path.relative(ROOT, shot).replace(/\\/g, '/') });

        expect(dom.h1Visible).toBe(1);
        expect(dom.scrollWidth).toBeLessThanOrEqual(dom.clientWidth + 1);
        expect(dom.mainWidth).toBeGreaterThan(0);
        expect(Math.abs(dom.mainWidth - dom.canvasWidth)).toBeLessThanOrEqual(1);
        expect(dom.pageWrapWidth).toBeGreaterThanOrEqual(dom.mainWidth);
        expect(dom.duplicateCssUrls).toEqual([]);
        expect(dom.bodyStylesheetUrls).toEqual([]);
        expect(dom.fixedInsideMain).toBe(0);
        expect(dom.rawIconNames).toEqual([]);
        expect(dom.operatorLeakage).toBe(false);
        expect(dom.postForms).toBeGreaterThan(0);
        expect(dom.resolvedTheme).toBe(theme);
        if (viewport.width < 992) {
          expect(dom.desktopSidebarDisplay).toBe('none');
          expect(dom.mobileSidebarOpen).toBe(false);
        }
        if (viewport.width <= 1024) {
          expect(dom.layoutColumns.trim().split(/\s+/)).toHaveLength(1);
        } else {
          expect(dom.layoutColumns.trim().split(/\s+/).length).toBeGreaterThanOrEqual(2);
        }

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

    // Exercise the real CSRF-protected POST endpoint. The pack service is
    // idempotent, so reruns update the demo tenant's installation rather than
    // manufacturing a simulated control or cross-tenant state.
    await page.locator('form[data-rmc-genuine-pack-action="1"] input[name="confirm"]').check();
    const actionResponsePromise = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && new URL(response.url()).pathname === '/school/setup/packs/'
    ));
    await page.locator('form[data-rmc-genuine-pack-action="1"] button[type="submit"]').click();
    const actionResponse = await actionResponsePromise;
    expect(actionResponse.status()).toBe(200);
    const nativeTable = page.locator('[data-rmc-native-table="1"] table.rmc-tpw-table');
    await expect(nativeTable).toBeVisible();
    expect(await nativeTable.evaluate((table) => getComputedStyle(table).display)).toBe('table');

    // The platform-wide re-audit found that shared theme-preview assets were
    // structurally correct in source but were being included by two page
    // bodies. Prove the repaired ownership against rendered tenant-host DOM,
    // at desktop/mobile widths and in both themes.
    const headOwnershipEvidence = [];
    for (const route of HEAD_OWNERSHIP_ROUTES) {
      for (const theme of ['dark', 'light']) {
        for (const viewport of [VIEWPORTS[0], VIEWPORTS[VIEWPORTS.length - 1]]) {
          await page.setViewportSize({ width: viewport.width, height: viewport.height });
          const response = await page.goto(`${TENANT_BASE_URL}${route.path}`, {
            waitUntil: 'domcontentloaded',
            timeout: 120000,
          });
          expect(response).not.toBeNull();
          expect(response.status(), route.path).toBe(200);
          expect(new URL(page.url()).hostname).toBe('demo-school.runmycampus.com');
          await page.evaluate((activeTheme) => {
            if (!window.RMCTheme || typeof window.RMCTheme.set !== 'function') {
              throw new Error('RMCTheme API unavailable');
            }
            window.RMCTheme.set(activeTheme);
          }, theme);
          await page.waitForTimeout(200);

          const dom = await page.evaluate(() => {
            const root = document.documentElement;
            const cssUrls = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
              .map((node) => node.href);
            const visibleH1 = Array.from(document.querySelectorAll('h1')).filter((node) => {
              const rect = node.getBoundingClientRect();
              const style = getComputedStyle(node);
              return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            });
            return {
              clientWidth: root.clientWidth,
              scrollWidth: root.scrollWidth,
              h1Visible: visibleH1.length,
              resolvedTheme: root.getAttribute('data-resolved-theme'),
              duplicateCssUrls: cssUrls.filter((url, index) => cssUrls.indexOf(url) !== index),
              bodyStylesheetUrls: Array.from(document.body.querySelectorAll('link[rel="stylesheet"]'))
                .map((node) => node.href),
              themePreviewCssInHead: document.head.querySelectorAll('link[href*="site-settings-preview.css"]').length,
              contrastGuardInHead: document.head.querySelectorAll('script[src*="contrast-guard.js"]').length,
              themePreviewScriptInHead: document.head.querySelectorAll('script[src*="site-settings-preview.js"]').length,
            };
          });

          expect(dom.scrollWidth).toBeLessThanOrEqual(dom.clientWidth + 1);
          expect(dom.h1Visible).toBe(1);
          expect(dom.resolvedTheme).toBe(theme);
          expect(dom.duplicateCssUrls).toEqual([]);
          expect(dom.bodyStylesheetUrls).toEqual([]);
          expect(dom.themePreviewCssInHead).toBe(1);
          expect(dom.contrastGuardInHead).toBe(1);
          expect(dom.themePreviewScriptInHead).toBe(1);

          const shot = path.join(EVIDENCE_DIR, `${route.slug}-${theme}-${viewport.name}.png`);
          await page.screenshot({ path: shot, fullPage: true });
          headOwnershipEvidence.push({
            route: route.path,
            theme,
            viewport,
            status: response.status(),
            url: page.url(),
            ...dom,
            screenshot: path.relative(ROOT, shot).replace(/\\/g, '/'),
          });
        }
      }
    }

    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'tenant-pack-full-canvas-browser-evidence.json'),
      `${JSON.stringify({ generatedAt: new Date().toISOString(), evidence, headOwnershipEvidence, environmentWarnings, consoleErrors, brokenResources, httpFailures }, null, 2)}\n`,
      'utf8',
    );
    expect(brokenResources).toEqual([]);
    expect(httpFailures).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
