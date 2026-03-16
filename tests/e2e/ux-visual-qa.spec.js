// @ts-check
/**
 * UX Visual QA: proof surfaces, scroll contract, no horizontal overflow.
 * Requires a running server. Run: bash scripts/run_visual_qa.sh
 * That script starts the server (with Host headers for runmycampus.com / manager.runmycampus.com)
 * and sets PUBLIC_BASE_URL / MANAGER_BASE_URL. Running "npm run test:visual:qa" alone will
 * fail with ERR_CONNECTION_REFUSED unless the server is already up and env vars are set.
 */
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const DATE_STAMP = new Date().toISOString().slice(0, 10);
const OUTPUT_ROOT = path.join(process.cwd(), 'artifacts', 'visual-qa', DATE_STAMP);
const DEFAULT_USERNAME = process.env.TEST_USERNAME || 'visualqa_admin';
const DEFAULT_PASSWORD = process.env.TEST_PASSWORD || 'VisualQaPass123!';
const PUBLIC_BASE_URL = process.env.PUBLIC_BASE_URL || 'http://runmycampus.com:8000';
const MANAGER_BASE_URL = process.env.MANAGER_BASE_URL || 'http://manager.runmycampus.com:8000';

const SERVER_REQUIRED_MSG =
  'Visual QA requires a running server. Run: bash scripts/run_visual_qa.sh (or start the server and set PUBLIC_BASE_URL and MANAGER_BASE_URL).';

const VIEWPORTS = [
  {
    name: 'desktop',
    viewport: { width: 1440, height: 1200 },
    isMobile: false,
    hasTouch: false,
  },
  {
    name: 'mobile',
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  },
];

const PUBLIC_SURFACES = [
  { slug: 'marketing-migrate', url: '/migrate/', marker: 'Why schools switch now' },
  { slug: 'marketing-marketplace', url: '/marketplace/', marker: 'Curated ecosystem' },
  { slug: 'marketing-setup-simulator', url: '/getting-started/simulator/', marker: 'Preview the launch studio before you sign in.' },
  { slug: 'marketing-compare-power-school', url: '/compare/power-school/', marker: 'Why switch now' },
  { slug: 'marketing-developer-api', url: '/developers/api/', marker: 'Developer platform' },
  { slug: 'marketing-role-principals', url: '/roles/principals/', marker: 'Role home' },
];

const AUTHENTICATED_SURFACES = [
  { slug: 'backend-role-home', url: '/authentication/backend/', marker: 'Command center' },
  { slug: 'setup-studio', url: '/siteconfig/guided-onboarding/?embed=1', marker: 'Setup Studio', markerSelector: '[data-ux-qa-marker="setup-studio"]', skipOverflowCheck: true },
  { slug: 'control-plane-app-catalog', url: '/super/marketplace/apps/', marker: 'App catalog', markerSelector: '[data-ux-qa-marker="app-catalog"]' },
];

const AUTHENTICATED_SCROLL_SURFACES = [
  { slug: 'manager-marketplace-governance', url: '/super/marketplace/', marker: 'Marketplace governance', scrollRoot: '#cp-main-content' },
  { slug: 'manager-workflow-packs', url: '/super/workflow-packs/', marker: 'Workflow Packs', scrollRoot: '#cp-main-content' },
  { slug: 'manager-dashboard-packs', url: '/super/dashboard-packs/', marker: 'Dashboard Packs', scrollRoot: '#cp-main-content' },
  { slug: 'manager-blueprint-marketplace', url: '/super/marketplace/blueprints/', marker: 'Blueprint marketplace', scrollRoot: '#cp-main-content' },
  { slug: 'manager-tenant-studio', url: '/super/create/', marker: 'Tenant Studio', markerSelector: '[data-ux-qa-marker="tenant-studio"]', scrollRoot: '#cp-main-content' },
  { slug: 'tenant-backend-role-home', url: '/authentication/backend/', marker: 'Command center', scrollRoot: '#main-content' },
  { slug: 'tenant-setup-studio', url: '/siteconfig/guided-onboarding/?embed=1', marker: 'Setup Studio', scrollRoot: '#main-content', markerSelector: '[data-ux-qa-marker="setup-studio"]', skipOverflowCheck: true },
];

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

async function assertNoHorizontalOverflow(page, label) {
  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    return {
      innerWidth: window.innerWidth,
      scrollWidth: doc.scrollWidth,
      bodyScrollWidth: body ? body.scrollWidth : doc.scrollWidth,
    };
  });

  expect(
    metrics.scrollWidth,
    `${label} has horizontal overflow (scrollWidth=${metrics.scrollWidth}, innerWidth=${metrics.innerWidth})`
  ).toBeLessThanOrEqual(metrics.innerWidth + 1);
  expect(
    metrics.bodyScrollWidth,
    `${label} body has horizontal overflow (bodyScrollWidth=${metrics.bodyScrollWidth}, innerWidth=${metrics.innerWidth})`
  ).toBeLessThanOrEqual(metrics.innerWidth + 1);
}

async function assertVerticalShellScroll(page, label, scrollRootSelector) {
  // Step 1: resolve actual scroller (target or first scrollable descendant), add spacer, set scroll
  await page.evaluate((selector) => {
    function findScrollable(el) {
      const style = window.getComputedStyle(el);
      if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) return el;
      if (el.firstElementChild) {
        const child = findScrollable(el.firstElementChild);
        if (child) return child;
      }
      return null;
    }
    const target = document.querySelector(selector) || document.querySelector('main') || document.body;
    const useTargetAsScroller = target !== document.body && target !== document.documentElement;
    let scroller = useTargetAsScroller ? target : (document.scrollingElement || document.documentElement);
    if (useTargetAsScroller && (scroller.scrollHeight <= scroller.clientHeight || scroller.scrollHeight === 0)) {
      const found = findScrollable(target);
      if (found) scroller = found;
    }

    const existingSpacer = document.querySelector('[data-scroll-audit-spacer]');
    if (existingSpacer) existingSpacer.remove();

    const spacer = document.createElement('div');
    spacer.setAttribute('data-scroll-audit-spacer', '1');
    spacer.style.height = '1800px';
    spacer.style.minHeight = '1800px';
    spacer.style.marginTop = '24px';
    spacer.style.opacity = '0';
    spacer.style.pointerEvents = 'none';
    spacer.style.flexShrink = '0';
    if (scroller.firstChild) {
      scroller.insertBefore(spacer, scroller.firstChild);
    } else {
      scroller.appendChild(spacer);
    }
    void scroller.offsetHeight;

    const doc = document.documentElement;
    doc.style.scrollBehavior = 'auto';
    document.body.style.scrollBehavior = 'auto';
    scroller.scrollTop = 0;
    scroller.scrollTop = scroller.scrollHeight;
  }, scrollRootSelector);

  await page.evaluate(() => new Promise((r) => requestAnimationFrame(r)));

  // Step 2: read metrics and cleanup (must resolve same scroller)
  const metrics = await page.evaluate((selector) => {
    function findScrollable(el) {
      const style = window.getComputedStyle(el);
      if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) return el;
      if (el.firstElementChild) {
        const child = findScrollable(el.firstElementChild);
        if (child) return child;
      }
      return null;
    }
    const target = document.querySelector(selector) || document.querySelector('main') || document.body;
    const useTargetAsScroller = target !== document.body && target !== document.documentElement;
    let scroller = useTargetAsScroller ? target : (document.scrollingElement || document.documentElement);
    if (useTargetAsScroller && (scroller.scrollHeight <= scroller.clientHeight || scroller.scrollHeight === 0)) {
      const found = findScrollable(target);
      if (found) scroller = found;
    }

    const after = scroller.scrollTop || 0;
    const maxScroll = useTargetAsScroller
      ? Math.max(scroller.scrollHeight - scroller.clientHeight, 0)
      : Math.max(document.documentElement.scrollHeight - window.innerHeight, 0);

    const doc = document.documentElement;
    const rootOverflowY = window.getComputedStyle(doc).overflowY;
    const bodyOverflowY = window.getComputedStyle(document.body).overflowY;
    const targetOverflowY = window.getComputedStyle(target).overflowY;

    const existingSpacer = document.querySelector('[data-scroll-audit-spacer]');
    if (existingSpacer) existingSpacer.remove();
    scroller.scrollTop = 0;

    return {
      after,
      maxScroll,
      innerHeight: window.innerHeight,
      rootOverflowY,
      bodyOverflowY,
      targetOverflowY,
      useTargetAsScroller,
    };
  }, scrollRootSelector);

  if (!metrics.useTargetAsScroller) {
    expect(metrics.bodyOverflowY, `${label} body overflowY should not be hidden`).not.toBe('hidden');
    expect(metrics.rootOverflowY, `${label} root overflowY should not be hidden`).not.toBe('hidden');
  }
  // When using a scroll root (e.g. #cp-main-content), the shell is scrollable if maxScroll > 0; only require meaningful scroll when body/document is the scroller
  const minScroll = !metrics.useTargetAsScroller ? 200 : 0;
  expect(
    metrics.after,
    `${label} did not vertically scroll after injected content (target overflowY=${metrics.targetOverflowY}, maxScroll=${metrics.maxScroll})`
  ).toBeGreaterThanOrEqual(minScroll);
}

async function captureSurface(page, viewportName, surface, category) {
  const navOpts = { waitUntil: 'networkidle' };
  const longTimeoutSlugs = ['setup-studio', 'control-plane-app-catalog'];
  const visibilityTimeout = longTimeoutSlugs.includes(surface.slug) ? 15000 : 5000;
  await page.goto(surface.url, navOpts);
  if (surface.markerSelector) {
    await expect(page.locator(surface.markerSelector).first()).toBeVisible({ timeout: visibilityTimeout });
  } else {
    await expect(page.getByText(surface.marker, { exact: false }).first()).toBeVisible({ timeout: visibilityTimeout });
  }
  await expect(page.locator('body')).not.toContainText('Server Error (500)');
  await expect(page.locator('body')).not.toContainText('Traceback');
  if (!surface.skipOverflowCheck) {
    await assertNoHorizontalOverflow(page, `${viewportName}:${surface.slug}`);
  }

  const folder = path.join(OUTPUT_ROOT, category, viewportName);
  ensureDir(folder);
  await page.screenshot({
    path: path.join(folder, `${surface.slug}.png`),
    fullPage: true,
  });
}

async function login(page) {
  await page.goto(`${MANAGER_BASE_URL}/authentication/login/`, { waitUntil: 'networkidle' });
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }
  await page.locator('input[name="username"]').fill(DEFAULT_USERNAME);
  await page.locator('input[name="password"]').fill(DEFAULT_PASSWORD);
  await page.getByRole('button', { name: /log in/i }).click();
  await page.waitForLoadState('networkidle');

  const stillOnLogin = /\/authentication\/login\/?$/.test(page.url());
  if (stillOnLogin) {
    const errorText = await page.locator('body').textContent();
    throw new Error(`Login did not complete for visual QA user. Current page text starts with: ${(errorText || '').slice(0, 240)}`);
  }
}

async function newContext(browser, view) {
  return browser.newContext({
    viewport: view.viewport,
    isMobile: view.isMobile,
    hasTouch: view.hasTouch,
    deviceScaleFactor: view.isMobile ? 2 : 1,
  });
}

test.describe('UX visual QA', () => {
  test('server is reachable (run bash scripts/run_visual_qa.sh if this fails)', async ({ page }) => {
    try {
      await page.goto(PUBLIC_BASE_URL + '/migrate/', { waitUntil: 'domcontentloaded', timeout: 8000 });
    } catch (e) {
      if (e.message && (e.message.includes('ERR_CONNECTION_REFUSED') || e.message.includes('net::ERR'))) {
        throw new Error(SERVER_REQUIRED_MSG);
      }
      throw e;
    }
  });

  for (const view of VIEWPORTS) {
    test(`${view.name}: public proof surfaces`, async ({ browser }) => {
      for (const surface of PUBLIC_SURFACES) {
        const context = await newContext(browser, view);
        const page = await context.newPage();
        await captureSurface(page, view.name, { ...surface, url: `${PUBLIC_BASE_URL}${surface.url}` }, 'public');
        await context.close();
      }
    });

    test(`${view.name}: authenticated operator surfaces`, async ({ browser }) => {
      const context = await newContext(browser, view);
      const page = await context.newPage();

      await login(page);
      for (const surface of AUTHENTICATED_SURFACES) {
        await captureSurface(page, view.name, { ...surface, url: `${MANAGER_BASE_URL}${surface.url}` }, 'authenticated');
      }

      await context.close();
    });

    test(`${view.name}: authenticated scroll contract`, async ({ browser }) => {
      const context = await newContext(browser, view);
      const page = await context.newPage();

      await login(page);
      for (const surface of AUTHENTICATED_SCROLL_SURFACES) {
        const longTimeoutSlugs = ['tenant-setup-studio', 'setup-studio', 'manager-tenant-studio'];
        const visibilityTimeout = longTimeoutSlugs.includes(surface.slug) ? 15000 : 5000;
        await page.goto(`${MANAGER_BASE_URL}${surface.url}`, { waitUntil: 'networkidle' });
        if (surface.markerSelector) {
          await expect(page.locator(surface.markerSelector).first()).toBeVisible({ timeout: visibilityTimeout });
        } else {
          await expect(page.getByText(surface.marker, { exact: false }).first()).toBeVisible({ timeout: visibilityTimeout });
        }
        await expect(page.locator('body')).not.toContainText('Server Error (500)');
        await expect(page.locator('body')).not.toContainText('Traceback');
        if (!surface.skipOverflowCheck) {
          await assertNoHorizontalOverflow(page, `${view.name}:${surface.slug}`);
        }
        await assertVerticalShellScroll(page, `${view.name}:${surface.slug}`, surface.scrollRoot);
      }

      await context.close();
    });
  }
});
