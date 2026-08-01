// @ts-check
/**
 * Real manager-host certification for the two operator workbenches repaired by
 * the 2026-07-31 full-canvas audit. The source sweep covers every template;
 * these real-browser probes prove host routing, shell ownership and responsive
 * behavior for the concrete low-confidence findings.
 */
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { ensureManagerHost } = require('./helpers/manager-login');

const ROOT = path.join(__dirname, '..', '..');
const EVIDENCE_DIR = path.join(
  ROOT,
  'artifacts',
  'design-approvals',
  'tenant-pack-full-canvas-implementation-2026-07-31',
  'operator-workbenches',
);
const ROUTES = process.env.RMC_OPERATOR_QUICK === '1' ? [
  { slug: 'provision-queue', path: '/super/provision-queue/' },
] : [
  { slug: 'provision-queue', path: '/super/provision-queue/' },
  { slug: 'support-live', path: '/super/support/live/' },
];
const HEAD_OWNERSHIP_ROUTES = [
  { slug: 'theme-colors', path: '/siteconfig/theme-colors/?standalone=1' },
  { slug: 'studio-experience', path: '/studio/experience/' },
];
const QUICK_WIDTH = Number(process.env.RMC_OPERATOR_QUICK_WIDTH || 1440);
const VIEWPORTS = process.env.RMC_OPERATOR_QUICK === '1' ? [
  { name: String(QUICK_WIDTH), width: QUICK_WIDTH, height: QUICK_WIDTH <= 390 ? 844 : 1000 },
] : [
  { name: '1440', width: 1440, height: 1000 },
  { name: '1024', width: 1024, height: 900 },
  { name: '768', width: 768, height: 900 },
  { name: '390', width: 390, height: 844 },
];

test.describe('operator audited workbenches', () => {
  test.setTimeout(360000);
  test.beforeAll(() => fs.mkdirSync(EVIDENCE_DIR, { recursive: true }));

  test('real manager host has one shell, responsive themes, and clean resources', async ({ page }) => {
    const consoleErrors = [];
    const environmentWarnings = [];
    const brokenResources = [];
    page.on('console', (message) => {
      if (message.type() !== 'error') return;
      const value = message.text();
      if (
        value.includes('Cross-Origin-Opener-Policy header has been ignored')
        || /WebSocket connection to 'ws:\/\/manager\.runmycampus\.com:\d+\/ws\//.test(value)
      ) {
        environmentWarnings.push(value);
        return;
      }
      consoleErrors.push(value);
    });
    page.on('response', (response) => {
      if (
        response.status() >= 400
        && /\.(?:css|js|png|jpe?g|svg|woff2?)(?:\?|$)/i.test(response.url())
      ) {
        brokenResources.push({ status: response.status(), url: response.url() });
      }
    });

    const evidence = [];
    for (const route of ROUTES) {
      const response = await page.goto(route.path, {
        waitUntil: 'domcontentloaded',
        timeout: 120000,
      });
      await ensureManagerHost(page);
      expect(response).not.toBeNull();
      expect(response.status(), route.path).toBe(200);
      expect(new URL(page.url()).hostname).toBe('manager.runmycampus.com');

      for (const theme of ['dark', 'light']) {
        for (const viewport of VIEWPORTS) {
          await page.setViewportSize({ width: viewport.width, height: viewport.height });
          await page.evaluate((activeTheme) => {
            if (!window.RMCTheme || typeof window.RMCTheme.set !== 'function') {
              throw new Error('RMCTheme API unavailable');
            }
            window.RMCTheme.set(activeTheme);
          }, theme);
          await page.waitForTimeout(150);

          const dom = await page.evaluate(() => {
            const root = document.documentElement;
            const main = document.querySelector('#cp-main-content, [data-rmc-shell-main="control-plane"]');
            const shell = document.querySelector('.rmc-app-shell');
            const canvas = document.querySelector('.rmc-app-shell__canvas');
            const sidebar = document.querySelector('.rmc-app-shell__sidebar');
            const cssUrls = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map((node) => node.href);
            const rawIconPattern = /^(?:chevron_(?:left|right|up|down)|more_vert|menu_open|close|settings)$/i;
            const rawIconNames = Array.from(document.querySelectorAll('body *'))
              .filter((node) => {
                const style = getComputedStyle(node);
                const isIconNode = node.matches(
                  '.material-icons, .material-icons-outlined, .material-symbols-outlined, .material-symbols-rounded, [data-rmc-icon-font]',
                ) || /material (?:icons|symbols)/i.test(style.fontFamily || '');
                return isIconNode
                  && style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && rawIconPattern.test((node.textContent || '').trim());
              })
              .map((node) => (node.textContent || '').trim());
            const visibleH1 = Array.from(document.querySelectorAll('h1')).filter((node) => {
              const rect = node.getBoundingClientRect();
              const style = getComputedStyle(node);
              return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            });
            const fixedInsideMain = main
              ? Array.from(main.querySelectorAll('*')).filter((node) => {
                const style = getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.position === 'fixed'
                  && !node.closest('.rmc-assist-dock, .rmc-copilot-mobile-fab, [data-rmc-back-to-top]')
                  && style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && Number(style.opacity || '1') > 0
                  && rect.width > 0
                  && rect.height > 0;
              }).map((node) => ({
                tag: node.tagName.toLowerCase(),
                id: node.id || '',
                classes: node.className && typeof node.className === 'string' ? node.className : '',
              }))
              : [{ tag: 'missing-main', id: '', classes: '' }];
            const visibleExpectedFixedControls = Array.from(
              document.querySelectorAll('.rmc-assist-dock, .rmc-copilot-mobile-fab, [data-rmc-back-to-top]'),
            ).filter((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.position === 'fixed'
                && style.display !== 'none'
                && style.visibility !== 'hidden'
                && rect.width > 0
                && rect.height > 0;
            }).map((node) => node.matches('.rmc-assist-dock') ? 'assist-dock'
              : node.matches('.rmc-copilot-mobile-fab') ? 'copilot-mobile-fab'
                : 'back-to-top');
            const visibleAssistDocks = Array.from(document.querySelectorAll('.rmc-assist-dock')).filter((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            }).length;
            const rect = (node) => {
              if (!node) return null;
              const value = node.getBoundingClientRect();
              return {
                left: Math.round(value.left * 100) / 100,
                right: Math.round(value.right * 100) / 100,
                width: Math.round(value.width * 100) / 100,
              };
            };
            return {
              clientWidth: root.clientWidth,
              scrollWidth: root.scrollWidth,
              h1Visible: visibleH1.length,
              operationalFrames: document.querySelectorAll('[data-rmc-operational-center-frame="1"]').length,
              duplicateCssUrls: cssUrls.filter((url, index) => cssUrls.indexOf(url) !== index),
              bodyStylesheetUrls: Array.from(document.body.querySelectorAll('link[rel="stylesheet"]')).map((node) => node.href),
              fixedInsideMain,
              visibleExpectedFixedControls,
              visibleAssistDocks,
              rawIconNames,
              resolvedTheme: root.getAttribute('data-resolved-theme'),
              shellGridTemplateColumns: shell ? getComputedStyle(shell).gridTemplateColumns : '',
              shellRect: rect(shell),
              canvasRect: rect(canvas),
              mainRect: rect(main),
              sidebarDisplay: sidebar ? getComputedStyle(sidebar).display : 'missing',
            };
          });

          expect(dom.scrollWidth).toBeLessThanOrEqual(dom.clientWidth + 1);
          expect(dom.h1Visible).toBe(1);
          expect(dom.operationalFrames).toBe(1);
          expect(dom.duplicateCssUrls).toEqual([]);
          expect(dom.bodyStylesheetUrls).toEqual([]);
          expect(dom.fixedInsideMain).toEqual([]);
          expect(new Set(dom.visibleExpectedFixedControls).size).toBe(dom.visibleExpectedFixedControls.length);
          expect(dom.visibleExpectedFixedControls.length).toBeLessThanOrEqual(3);
          expect(dom.visibleAssistDocks).toBeLessThanOrEqual(1);
          expect(dom.rawIconNames).toEqual([]);
          expect(dom.resolvedTheme).toBe(theme);
          expect(dom.shellRect).not.toBeNull();
          expect(dom.canvasRect).not.toBeNull();
          expect(dom.mainRect).not.toBeNull();
          expect(dom.shellRect.left).toBeGreaterThanOrEqual(-1);
          expect(dom.shellRect.right).toBeLessThanOrEqual(dom.clientWidth + 1);
          if (viewport.width <= 1024) {
            expect(dom.shellGridTemplateColumns).toBe(`${dom.clientWidth}px`);
            expect(dom.sidebarDisplay).toBe('none');
            expect(dom.canvasRect.left).toBeLessThanOrEqual(1);
            expect(dom.canvasRect.width).toBeGreaterThanOrEqual(dom.clientWidth - 1);
            expect(dom.mainRect.width).toBeGreaterThanOrEqual(dom.clientWidth - 2);
          }

          const shot = path.join(EVIDENCE_DIR, `${route.slug}-${theme}-${viewport.name}.png`);
          await page.screenshot({ path: shot, fullPage: true });
          evidence.push({
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

    // Shared theme-preview assets must be owned by <head> on both manager
    // surfaces that render them. This browser proof complements the global
    // template parser audit and prevents body-level CSS/script regressions.
    const headOwnershipEvidence = [];
    for (const route of HEAD_OWNERSHIP_ROUTES) {
      for (const theme of ['dark', 'light']) {
        for (const viewport of [VIEWPORTS[0], VIEWPORTS[VIEWPORTS.length - 1]]) {
          await page.setViewportSize({ width: viewport.width, height: viewport.height });
          const response = await page.goto(route.path, {
            waitUntil: 'domcontentloaded',
            timeout: 120000,
          });
          await ensureManagerHost(page);
          expect(response).not.toBeNull();
          expect(response.status(), route.path).toBe(200);
          expect(new URL(page.url()).hostname).toBe('manager.runmycampus.com');
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
      path.join(EVIDENCE_DIR, 'operator-workbench-browser-evidence.json'),
      `${JSON.stringify({ generatedAt: new Date().toISOString(), evidence, headOwnershipEvidence, environmentWarnings, consoleErrors, brokenResources }, null, 2)}\n`,
      'utf8',
    );
    expect(brokenResources).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
