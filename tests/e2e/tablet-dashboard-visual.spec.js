// @ts-check
/**
 * Tablet proof (768 / 1024): backend command rail + parent dashboard — overflow + scroll contract.
 *
 * Requires Django on 127.0.0.1 with tenant subdomain host routing:
 *   MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8000
 *   Prefer a live tenant host (apple-class-qa when demo-school is missing).
 *
 *   PLAYWRIGHT_TENANT_BASE_URL=http://apple-class-qa.runmycampus.com:8000 \
 *     npx playwright test tests/e2e/tablet-dashboard-visual.spec.js
 */
const { test, expect } = require('@playwright/test');
const { qaTotpToken } = require('./helpers/apple-class-login');

const TENANT_BASE = (
  process.env.PLAYWRIGHT_TENANT_BASE_URL ||
  process.env.PLAYWRIGHT_BASE_URL ||
  'http://gilead-school.runmycampus.com:8000'
).replace(/\/$/, '');

const ADMIN_USER = process.env.TABLET_QA_ADMIN_USER || 'admin';
const ADMIN_PASSWORDS = process.env.TABLET_QA_ADMIN_PASSWORD
  ? [process.env.TABLET_QA_ADMIN_PASSWORD]
  : ['Sch00l_1234', 'AppleQaPass123!', 'Test1234', 'changeme'];
const PARENT_USER = process.env.TABLET_QA_PARENT_USER || 'Parent1';
const PARENT_PASSWORDS = process.env.TABLET_QA_PARENT_PASSWORD
  ? [process.env.TABLET_QA_PARENT_PASSWORD]
  : [
      process.env.ADMIN_PASSWORD,
      process.env.VISUAL_QA_TENANT_PASSWORD,
      'Test1234',
      'AppleQaPass123!',
      'Sch00l_1234',
      'changeme',
    ].filter(Boolean);

const TABLET_VIEWPORTS = [
  { name: 'tablet-portrait', width: 768, height: 1024 },
  { name: 'tablet-landscape', width: 1024, height: 768 },
];

const SURFACES = [
  {
    slug: 'tenant-backend',
    path: '/authentication/backend/',
    expectSelector: 'body.backend-shell, .backend-v2-workbench, .backend-role-home',
    scrollRoot: '#main-content',
    role: 'staff',
    username: ADMIN_USER,
    passwords: ADMIN_PASSWORDS,
  },
  {
    slug: 'tenant-parent',
    path: '/portal/parent/',
    marker: /parent|home|dashboard|child/i,
    scrollRoot: '#main-content',
    role: 'parent',
    username: PARENT_USER,
    passwords: PARENT_PASSWORDS.length ? PARENT_PASSWORDS : ['Test1234'],
  },
];

test.use({ baseURL: TENANT_BASE });

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
    `${label} document overflow (scrollWidth=${metrics.scrollWidth}, inner=${metrics.innerWidth})`
  ).toBeLessThanOrEqual(metrics.innerWidth + 1);
  expect(
    metrics.bodyScrollWidth,
    `${label} body overflow (bodyScrollWidth=${metrics.bodyScrollWidth}, inner=${metrics.innerWidth})`
  ).toBeLessThanOrEqual(metrics.innerWidth + 1);
}

async function assertLayoutContract(page, label, scrollRootSel) {
  const armed = await page.evaluate(
    () => document.documentElement.getAttribute('data-rmc-reveal-armed') === '1'
  );
  if (!armed) {
    await page.evaluate(() => {
      document.documentElement.setAttribute('data-rmc-reveal-armed', '1');
    });
  }
  const audit = await page.evaluate((sel) => {
    function findScrollable(el) {
      if (!el) return null;
      const style = window.getComputedStyle(el);
      if (
        (style.overflowY === 'auto' ||
          style.overflowY === 'scroll' ||
          style.overflowY === 'overlay') &&
        el.scrollHeight > el.clientHeight + 2
      ) {
        return el;
      }
      for (let i = 0; i < el.children.length; i++) {
        const found = findScrollable(el.children[i]);
        if (found) return found;
      }
      return el;
    }
    function countStranded() {
      let stranded = 0;
      document.querySelectorAll('.rmc-reveal').forEach((el) => {
        if (el.classList.contains('is-revealed')) return;
        if (parseFloat(getComputedStyle(el).opacity) < 0.05) stranded += 1;
      });
      return stranded;
    }
    const main = findScrollable(document.querySelector(sel));
    const body = document.body;
    const bodyOY = body ? getComputedStyle(body).overflowY : '';
    if (main && main.scrollHeight > main.clientHeight + 2) {
      main.scrollTop = Math.max(0, main.scrollHeight - main.clientHeight);
      main.dispatchEvent(new Event('scroll', { bubbles: true }));
    }
    const strandedAfter = countStranded();
    const trapped =
      bodyOY === 'hidden' &&
      body &&
      body.scrollHeight > body.clientHeight + 80 &&
      main &&
      !(main.scrollHeight > main.clientHeight + 2);
    const failures = [];
    if (trapped) failures.push('body_scroll_trapped');
    if (main && main.scrollHeight > main.clientHeight + 100 && strandedAfter > 0) {
      failures.push(`scrollable_but_stranded_${strandedAfter}`);
    }
    return { failures, strandedAfter, armed: document.documentElement.getAttribute('data-rmc-reveal-armed') };
  }, scrollRootSel);
  expect(audit.failures, `${label} layout failures`).toEqual([]);
}

async function dismissSessionOverlays(page) {
  const securityDismiss = page.getByRole('button', { name: /dismiss for this session/i });
  if (await securityDismiss.count()) {
    await securityDismiss.click({ timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(300);
  }
}

async function completeMfaIfNeeded(page, username) {
  let url = page.url();
  if (/\/authentication\/mfa\/setup/i.test(url)) {
    throw new Error(
      `MFA setup still required for ${username}; run: python scripts/verify_tablet_dashboard_visual_completion.py`,
    );
  }
  if (/\/authentication\/mfa\/verify/i.test(url)) {
    const token = qaTotpToken(username);
    await page.locator('input[name="token"]').fill(token);
    await page.getByRole('button', { name: /verify|continue|submit/i }).click();
    await page.waitForURL((u) => !/\/authentication\/mfa\/verify/i.test(u.pathname), {
      timeout: 45000,
    });
    url = page.url();
    if (/\/authentication\/mfa\/setup/i.test(url)) {
      throw new Error(`MFA setup required for ${username} after verify`);
    }
  }
}

async function reachSurface(page, surface) {
  const res = await page.goto(surface.path, {
    waitUntil: 'domcontentloaded',
    timeout: 90000,
  });
  expect(res?.status() ?? 500).toBeLessThan(500);
  await completeMfaIfNeeded(page, surface.username);
  if (!new RegExp(surface.path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(page.url())) {
    await page.goto(surface.path, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await completeMfaIfNeeded(page, surface.username);
  }
  await dismissSessionOverlays(page);
}

async function loginTenant(page, surface) {
  const passwords = surface.passwords || [];
  let lastError = '';
  for (const password of passwords) {
    await page.goto('/authentication/login/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    const roleSelect = page.locator('select[name="role"]');
    if (await roleSelect.count()) {
      await roleSelect.selectOption(surface.role);
    }
    await page.locator('input[name="username"]').fill(surface.username);
    await page.locator('input[name="password"]').fill(password);
    await page.getByRole('button', { name: /log in/i }).click();
    try {
      await page.waitForURL((u) => !/\/authentication\/login\/?$/i.test(u.pathname), {
        timeout: 45000,
      });
      await completeMfaIfNeeded(page, surface.username);
      return;
    } catch (err) {
      lastError = String(err);
    }
  }
  throw new Error(
    `Tenant login failed for ${surface.username}@${TENANT_BASE} (${surface.role}). Last: ${lastError}`
  );
}

test.describe('Tablet dashboard visual proof', () => {
  test('tenant host is reachable', async ({ page }) => {
    const res = await page.goto('/authentication/login/', {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });
    expect(res?.status() ?? 500).toBeLessThan(500);
  });

  for (const view of TABLET_VIEWPORTS) {
    for (const surface of SURFACES) {
      test(`${view.name}: ${surface.slug}`, async ({ browser }) => {
    test.setTimeout(120000);
        const context = await browser.newContext({
          viewport: { width: view.width, height: view.height },
          isMobile: view.width < 992,
          hasTouch: view.width < 992,
        });
        const page = await context.newPage();
        await loginTenant(page, surface);
        await reachSurface(page, surface);
        await expect(page.locator('body')).not.toContainText('Server Error (500)');
        await expect(page.locator('body')).not.toContainText('Traceback');
        if (surface.expectSelector) {
          await expect(page.locator(surface.expectSelector).first()).toBeVisible({
            timeout: 20000,
          });
        } else {
          await expect(page.getByText(surface.marker).first()).toBeVisible({
            timeout: 15000,
          });
        }
        await page.waitForTimeout(800);
        const label = `${view.name}:${surface.slug}`;
        await assertNoHorizontalOverflow(page, label);
        await assertLayoutContract(page, label, surface.scrollRoot);
        await context.close();
      });
    }
  }
});
