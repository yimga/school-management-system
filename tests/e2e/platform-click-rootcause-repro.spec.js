// @ts-check
/**
 * Platform-wide click regression repro.
 *
 * This is intentionally browser-level: each assertion starts from a real route,
 * clicks a visible page element, and requires either navigation or an opened UI
 * panel. It also records console/page errors and screenshots for root-cause work.
 *
 * Run:
 *   VISUAL_QA_PORT=8000 npx playwright test tests/e2e/platform-click-rootcause-repro.spec.js
 */
const { test, expect } = require('@playwright/test');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const PORT = process.env.VISUAL_QA_PORT || '8000';
const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL || `http://runmycampus.com:${PORT}`;
const MANAGER_BASE_URL =
  process.env.MANAGER_BASE_URL || `http://manager.runmycampus.com:${PORT}`;
const TENANT_PREFIX = process.env.TENANT_PREFIX || '';
const TENANT_BASE_URL =
  process.env.TENANT_BASE_URL || `http://apple-class-qa.runmycampus.com:${PORT}`;
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');
const REPO_ROOT = path.join(__dirname, '..', '..');
const TOTP_SCRIPT = path.join(REPO_ROOT, 'scripts', 'apple_class_qa_totp.py');
const CLICKS_PER_SURFACE = 3;

const MANAGER_USERNAME = process.env.VISUAL_QA_USERNAME || 'visualqa_admin';
const MANAGER_PASSWORD = process.env.VISUAL_QA_PASSWORD || 'VisualQaPass123!';
const TENANT_USERNAME =
  process.env.TENANT_E2E_USERNAME || process.env.APPLE_QA_TENANT_USERNAME || 'appleqa_tenant';
const TENANT_PASSWORD =
  process.env.TENANT_E2E_PASSWORD || process.env.APPLE_QA_TENANT_PASSWORD || 'AppleQaPass123!';

const surfaces = [
  {
    slug: 'marketing',
    baseUrl: MARKETING_BASE_URL,
    path: '/',
    auth: null,
  },
  {
    slug: 'manager-super',
    baseUrl: MANAGER_BASE_URL,
    path: '/super/',
    auth: 'manager',
  },
  {
    slug: 'control-plane',
    baseUrl: MANAGER_BASE_URL,
    path: '/configuration/',
    auth: 'manager',
  },
  {
    slug: 'unfold-admin',
    baseUrl: MANAGER_BASE_URL,
    path: '/admin/',
    auth: 'manager',
  },
  {
    slug: 'tenant-portal',
    baseUrl: TENANT_BASE_URL,
    path: `${TENANT_PREFIX}/`,
    loginPath: `${TENANT_PREFIX}/authentication/login/`,
    auth: 'tenant',
  },
];

function absoluteUrl(baseUrl, route) {
  return new URL(route, baseUrl).toString();
}

async function gotoWithRetry(page, url, options) {
  let lastError = null;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      return await page.goto(url, options);
    } catch (error) {
      lastError = error;
      if (!String(error && error.message).includes('ERR_CONNECTION_REFUSED')) {
        throw error;
      }
      await page.waitForTimeout(2000);
    }
  }
  throw lastError;
}

async function login(page, baseUrl, username, password, loginPath = '/authentication/login/') {
  await gotoWithRetry(page, absoluteUrl(baseUrl, loginPath), {
    waitUntil: 'domcontentloaded',
    timeout: 90000,
  });
  if ((await page.locator('input[name="username"]').count()) === 0) {
    return;
  }
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /log in/i }).click();
  await page.waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), {
    timeout: 90000,
    waitUntil: 'domcontentloaded',
  });
  if (/\/authentication\/mfa\/verify\/?$/i.test(new URL(page.url()).pathname)) {
    const token = execFileSync('python', [TOTP_SCRIPT, username], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      env: process.env,
    }).trim();
    await page.locator('input[name="token"]').fill(token);
    await page.getByRole('button', { name: /verify|continue|submit/i }).click();
    await page.waitForURL((url) => !/\/authentication\/mfa\/verify\/?$/i.test(url.pathname), {
      timeout: 90000,
      waitUntil: 'domcontentloaded',
    });
  }
}

async function ensureAuth(page, surface, authenticatedPlanes) {
  if (!surface.auth || authenticatedPlanes.has(surface.auth)) {
    return;
  }
  if (surface.auth === 'manager') {
    await login(page, surface.baseUrl, MANAGER_USERNAME, MANAGER_PASSWORD);
  }
  if (surface.auth === 'tenant') {
    await login(page, surface.baseUrl, TENANT_USERNAME, TENANT_PASSWORD, surface.loginPath);
  }
  authenticatedPlanes.add(surface.auth);
}

async function collectClickTargets(page) {
  return page.evaluate(() => {
    const viewportW = window.innerWidth;
    const viewportH = window.innerHeight;
    const samePath = (href) => {
      try {
        const current = new URL(window.location.href);
        const target = new URL(href, current);
        return current.pathname === target.pathname && current.search === target.search;
      } catch (_) {
        return true;
      }
    };
    const visible = (el) => {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return (
        style.visibility !== 'hidden' &&
        style.display !== 'none' &&
        style.pointerEvents !== 'none' &&
        rect.width >= 8 &&
        rect.height >= 8 &&
        rect.bottom > 0 &&
        rect.right > 0 &&
        rect.top < viewportH &&
        rect.left < viewportW
      );
    };
    const label = (el) =>
      (
        el.getAttribute('aria-label') ||
        el.getAttribute('title') ||
        el.textContent ||
        el.id ||
        el.className ||
        el.tagName
      )
        .toString()
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 80);
    const selectorFor = (el, index) => {
      el.setAttribute('data-rmc-click-repro-target', String(index));
      return `[data-rmc-click-repro-target="${index}"]`;
    };

    const raw = Array.from(
      document.querySelectorAll('a[href], button, [role="button"], summary')
    ).filter((el) => {
      if (!visible(el)) return false;
      if (el.matches('[disabled], [aria-disabled="true"]')) return false;
      const text = label(el);
      if (/logout|delete|remove|danger|dismiss|close|verify|continue/i.test(text)) return false;
      if (/^RunMyCampus$/i.test(text)) return false;
      if (el.matches('.cp-topbar-bell')) return false;
      if (el.matches('.rmc-brand-mark-link')) return false;
      if (
        el.tagName.toLowerCase() === 'button' &&
        (el.getAttribute('type') || 'submit').toLowerCase() === 'submit'
      ) {
        return false;
      }
      if (el.tagName.toLowerCase() !== 'a' && el.tagName.toLowerCase() !== 'summary') {
        const hasExplicitAction =
          el.hasAttribute('data-bs-toggle') ||
          el.hasAttribute('data-rmc-kbd-cheatsheet-trigger') ||
          el.hasAttribute('aria-controls') ||
          el.hasAttribute('aria-expanded');
        if (!hasExplicitAction) return false;
      }
      if (el.tagName.toLowerCase() === 'a') {
        const href = el.getAttribute('href') || '';
        if (!href || href === '#' || /^javascript:/i.test(href)) return false;
        if (/logout|delete|remove|dismiss|close/i.test(href)) return false;
        if (/^(mailto|tel):/i.test(href)) return false;
        if (/^Home$/i.test(text) && /\/authentication\/redirect\/?$/i.test(href)) {
          return false;
        }
        const current = new URL(window.location.href);
        const target = new URL(href, current);
        if (target.origin !== current.origin) return false;
        if (
          target.href.replace(/#.*$/, '') === current.href.replace(/#.*$/, '')
        ) {
          return false;
        }
        if (samePath(href) && !el.hasAttribute('data-bs-toggle')) return false;
      }
      return true;
    });

    const seen = new Set();
    return raw
      .filter((el) => {
        const key = `${el.tagName}:${label(el)}:${el.getAttribute('href') || ''}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 5)
      .map((el, index) => ({
        selector: selectorFor(el, index),
        label: label(el),
        tagName: el.tagName.toLowerCase(),
        href: el.getAttribute('href') || '',
        ariaExpanded: el.getAttribute('aria-expanded') || '',
        className: String(el.className || ''),
      }));
  });
}

async function visibleOpenPanelCount(page) {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      return await page.evaluate(() => {
        const isVisible = (el) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return (
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            rect.width > 0 &&
            rect.height > 0
          );
        };
        return Array.from(
          document.querySelectorAll(
            '[aria-expanded="true"], [open], .show, .open, .dropdown-menu.show, .collapse.show'
          )
        ).filter(isVisible).length;
      });
    } catch (error) {
      if (!String(error && error.message).includes('Execution context was destroyed')) {
        throw error;
      }
      await page.waitForLoadState('domcontentloaded', { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(250);
    }
  }
  return 0;
}

async function clickAndAssert(page, surface, targetIndex, diagnostics) {
  await gotoWithRetry(page, absoluteUrl(surface.baseUrl, surface.path), {
    waitUntil: 'domcontentloaded',
    timeout: 90000,
  });
  await expect(page.locator('body')).toBeVisible({ timeout: 30000 });

  const targets = await collectClickTargets(page);
  expect(
    targets.length,
    `${surface.slug} must expose at least 5 visible click targets`
  ).toBeGreaterThanOrEqual(5);
  const target = targets[targetIndex];
  const beforeUrl = page.url();
  const beforeOpenPanels = await visibleOpenPanelCount(page);
  const locator = page.locator(target.selector).first();
  await expect(locator, `${surface.slug} target ${targetIndex + 1}`).toBeVisible();

  const navigation = page
    .waitForURL((url) => url.toString() !== beforeUrl, {
      timeout: 20000,
      waitUntil: 'domcontentloaded',
    })
    .catch(() => null);
  await locator.click({ timeout: 15000, noWaitAfter: true });
  await navigation;
  await page.waitForLoadState('domcontentloaded', { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(3000);

  const afterUrl = page.url();
  const afterOpenPanels = await visibleOpenPanelCount(page);
  const targetStillExists = (await locator.count()) > 0;
  const afterExpanded = targetStillExists
    ? await locator.getAttribute('aria-expanded').catch(() => null)
    : null;
  const changed = Boolean(
    afterUrl !== beforeUrl ||
      afterOpenPanels > beforeOpenPanels ||
      (target.ariaExpanded && afterExpanded !== target.ariaExpanded)
  );

  const screenshot = path.join(
    SCREENSHOT_DIR,
    `${surface.slug}-${String(targetIndex + 1).padStart(2, '0')}.png`
  );
  await page.screenshot({ path: screenshot, fullPage: true });

  diagnostics.push({
    surface: surface.slug,
    target: target.label,
    href: target.href,
    beforeUrl,
    afterUrl,
    beforeOpenPanels,
    afterOpenPanels,
    changed,
  });

  expect(
    changed,
    `${surface.slug} click ${targetIndex + 1} (${target.label}) must navigate or open a panel`
  ).toBeTruthy();
}

test.describe('platform click root-cause repro', () => {
  test.describe.configure({ mode: 'serial', timeout: 600000 });
  test.use({ viewport: { width: 1366, height: 900 } });

  test('15/15 clicks across manager, control-plane, tenant, admin, and marketing succeed', async ({
    page,
  }) => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    const diagnostics = [];
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(`${msg.type()}: ${msg.text()}`);
      }
    });
    page.on('pageerror', (error) => {
      consoleErrors.push(`pageerror: ${error.message}`);
    });

    const authenticatedPlanes = new Set();
    for (const surface of surfaces) {
      await ensureAuth(page, surface, authenticatedPlanes);
      for (let index = 0; index < CLICKS_PER_SURFACE; index += 1) {
        await clickAndAssert(page, surface, index, diagnostics);
      }
    }

    test.info().attach('click-diagnostics', {
      body: JSON.stringify({ diagnostics, consoleErrors }, null, 2),
      contentType: 'application/json',
    });
    fs.writeFileSync(
      path.join(SCREENSHOT_DIR, 'click-diagnostics-latest.json'),
      JSON.stringify({ diagnostics, consoleErrors }, null, 2)
    );
    const hardErrors = consoleErrors.filter((line) =>
      /pageerror:|Uncaught|TypeError|ReferenceError|is not a function|Cannot read prop/i.test(line)
    );
    expect(hardErrors, 'browser script exceptions').toEqual([]);
  });
});
