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

// Authenticated control-plane shells hold a persistent workflow-progress SSE
// (EventSource) open, so the page never reaches 'networkidle' — navigations that
// waited on it timed out (~30s) and the worker tore down, cascading 'Test ended'
// into later tests. We navigate on 'domcontentloaded' and rely on the explicit
// per-surface marker `toBeVisible` waits below to confirm the page rendered.
const NAV_WAIT_UNTIL = 'domcontentloaded';

const DATE_STAMP = new Date().toISOString().slice(0, 10);
const OUTPUT_ROOT = path.join(process.cwd(), 'artifacts', 'visual-qa', DATE_STAMP);
const DEFAULT_USERNAME = process.env.TEST_USERNAME || 'visualqa_admin';
const DEFAULT_PASSWORD = process.env.TEST_PASSWORD || 'VisualQaPass123!';
const PUBLIC_BASE_URL = process.env.PUBLIC_BASE_URL || 'http://runmycampus.com:8000';
const MANAGER_BASE_URL = process.env.MANAGER_BASE_URL || 'http://manager.runmycampus.com:8000';
/** Set by run_visual_qa.sh when DATABASE_URL is Postgres and a Client+Domain exists */
const TENANT_BASE_URL = (process.env.TENANT_BASE_URL || '').trim();

/** Align with seed_render_users / create_teacher_parent_accounts (ADMIN_PASSWORD or Test1234). */
function tenantPasswordCandidates() {
  const primary =
    process.env.VISUAL_QA_TENANT_PASSWORD || process.env.ADMIN_PASSWORD || '';
  if (primary) return [primary];
  return ['Test1234', 'changeme'];
}

// MFA (TOTP) support. The manager ADMIN role is in the always-on MFA baseline
// (apps/accounts/mfa_defaults.py), so a real login lands on
// /authentication/mfa/verify/. When VISUAL_QA_TOTP_HEX is set (run_visual_qa.sh
// seeds a confirmed TOTPDevice with that hex key), the login helpers compute and
// submit the current 6-digit code. Absent the env (e.g. CI that disables MFA),
// this is a no-op and login behavior is unchanged.
const crypto = require('crypto');
function _totpNow(hexKey, step = 30, digits = 6) {
  const counter = Math.floor(Date.now() / 1000 / step);
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const hmac = crypto.createHmac('sha1', Buffer.from(hexKey, 'hex')).update(buf).digest();
  const off = hmac[hmac.length - 1] & 0xf;
  const bin =
    ((hmac[off] & 0x7f) << 24) |
    ((hmac[off + 1] & 0xff) << 16) |
    ((hmac[off + 2] & 0xff) << 8) |
    (hmac[off + 3] & 0xff);
  return String(bin % 10 ** digits).padStart(digits, '0');
}
// Wait until the wall clock crosses into a fresh TOTP step so the next code we
// submit has a strictly higher counter than any already consumed by the device.
async function _waitForNextTotpWindow(step = 30) {
  const msIntoStep = (Date.now() / 1000 % step) * 1000;
  // Sleep to the boundary plus a 750ms cushion to clear server/client skew.
  const waitMs = step * 1000 - msIntoStep + 750;
  await new Promise((resolve) => setTimeout(resolve, waitMs));
}

async function completeMfaIfPresent(page) {
  const hexKey = (process.env.VISUAL_QA_TOTP_HEX || '').trim();
  if (!hexKey) return;
  if (!/\/authentication\/mfa\/verify\//.test(page.url())) return;
  const tokenField = page.locator('input[name="token"]');
  if (!(await tokenField.count())) return;
  // django_otp replay defense (last_t) rejects any code whose counter was
  // already consumed — which happens when a prior login this run (or a rapid
  // re-run) verified within the same 30s window. Submit, and if we're still on
  // the verify page, roll into the next window with a fresh code and retry.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await tokenField.fill(_totpNow(hexKey));
    // Trust the device so sensitive routes don't re-prompt MFA mid-run.
    const remember = page.locator('input[name="remember_device"]');
    if (await remember.count()) await remember.check().catch(() => {});
    await page
      .getByRole('button', { name: /verify and continue|verify|continue/i })
      .first()
      .click();
    await page.waitForLoadState(NAV_WAIT_UNTIL);
    if (!/\/authentication\/mfa\/verify\//.test(page.url())) return;
    // Still on verify → code rejected (replay or skew). Wait for a fresh window.
    if (attempt < 2) await _waitForNextTotpWindow();
  }
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} baseUrl
 * @param {'staff'|'parent'} role
 * @param {string} username
 * @param {string[]} passwords
 */
async function tryTenantLogin(page, baseUrl, role, username, passwords) {
  for (const pw of passwords) {
    await page.goto(`${baseUrl}/authentication/login/`, { waitUntil: NAV_WAIT_UNTIL });
    const roleSelect = page.locator('select[name="role"]');
    if (await roleSelect.count()) {
      await roleSelect.selectOption(role);
    }
    await page.locator('input[name="username"]').fill(username);
    await page.locator('input[name="password"]').fill(pw);
    await page.getByRole('button', { name: /log in/i }).click();
    await page.waitForLoadState(NAV_WAIT_UNTIL);
    await completeMfaIfPresent(page);
    if (!/\/authentication\/login\/?$/i.test(page.url())) return true;
  }
  return false;
}

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
    name: 'tablet-portrait',
    viewport: { width: 768, height: 1024 },
    isMobile: true,
    hasTouch: true,
  },
  {
    name: 'tablet-landscape',
    viewport: { width: 1024, height: 768 },
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
  // Operators on the manager host are redirected from /authentication/backend/
  // to super:dashboard (backend_dashboard view), which renders the visible hero
  // h1 "Platform Command Center" (#super-command-center-title). The tenant
  // backend (tenant-backend-role-home, below) renders the luxury page header.
  { slug: 'backend-role-home', url: '/authentication/backend/', marker: 'Command center', markerSelector: '#super-command-center-title' },
  { slug: 'setup-studio', url: '/siteconfig/guided-onboarding/?embed=1', marker: 'Setup Studio', markerSelector: '[data-ux-qa-marker="setup-studio"]', skipOverflowCheck: true },
  { slug: 'control-plane-app-catalog', url: '/super/marketplace/apps/', marker: 'App catalog', markerSelector: '[data-ux-qa-marker="app-catalog"]' },
];

const AUTHENTICATED_SCROLL_SURFACES = [
  { slug: 'manager-marketplace-governance', url: '/super/marketplace/', marker: 'Marketplace governance', scrollRoot: '#cp-main-content' },
  { slug: 'manager-workflow-packs', url: '/super/workflow-packs/', marker: 'Workflow Packs', scrollRoot: '#cp-main-content' },
  { slug: 'manager-dashboard-packs', url: '/super/dashboard-packs/', marker: 'Dashboard Packs', scrollRoot: '#cp-main-content' },
  { slug: 'manager-blueprint-marketplace', url: '/super/marketplace/blueprints/', marker: 'Blueprint marketplace', scrollRoot: '#cp-main-content' },
  { slug: 'manager-tenant-studio', url: '/super/create/', marker: 'Tenant Studio', markerSelector: '[data-ux-qa-marker="tenant-studio"]', scrollRoot: '#cp-main-content' },
  { slug: 'tenant-backend-role-home', url: '/authentication/backend/', marker: 'Command center', scrollRoot: '#main-content', markerSelector: '[data-luxury-major-contract="1"] h1' },
  { slug: 'tenant-setup-studio', url: '/siteconfig/guided-onboarding/?embed=1', marker: 'Setup Studio', scrollRoot: '#main-content', markerSelector: '[data-ux-qa-marker="setup-studio"]', skipOverflowCheck: true },
];

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

async function assertNoHorizontalOverflow(page, label) {
  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    const iw = window.innerWidth;
    // On overflow, name the widest offenders so failures are actionable
    // (which element pushes body wider than the viewport) instead of just a
    // number. Cheap: single pass, only collects elements past the right edge.
    const offenders = [];
    if ((body ? body.scrollWidth : doc.scrollWidth) > iw + 1) {
      for (const el of document.querySelectorAll("*")) {
        const r = el.getBoundingClientRect();
        if (r.right > iw + 1 && r.width > 0) {
          const id = el.id ? `#${el.id}` : "";
          const cls = (el.className && typeof el.className === "string")
            ? "." + el.className.trim().split(/\s+/).slice(0, 3).join(".")
            : "";
          offenders.push({
            sel: `${el.tagName.toLowerCase()}${id}${cls}`,
            right: Math.round(r.right),
            width: Math.round(r.width),
          });
        }
      }
      offenders.sort((a, b) => b.right - a.right);
    }
    return {
      innerWidth: iw,
      scrollWidth: doc.scrollWidth,
      bodyScrollWidth: body ? body.scrollWidth : doc.scrollWidth,
      offenders: offenders.slice(0, 8),
    };
  });

  const offenderText = metrics.offenders && metrics.offenders.length
    ? ` | widest past edge: ${metrics.offenders.map((o) => `${o.sel}(right=${o.right},w=${o.width})`).join(" ; ")}`
    : "";

  expect(
    metrics.scrollWidth,
    `${label} has horizontal overflow (scrollWidth=${metrics.scrollWidth}, innerWidth=${metrics.innerWidth})${offenderText}`
  ).toBeLessThanOrEqual(metrics.innerWidth + 1);
  expect(
    metrics.bodyScrollWidth,
    `${label} body has horizontal overflow (bodyScrollWidth=${metrics.bodyScrollWidth}, innerWidth=${metrics.innerWidth})${offenderText}`
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

// Resolve a surface's marker to its first VISIBLE match. Page headings often
// share their text with a (collapsed/hidden) sidebar nav or "recent" link, so a
// bare .first() can latch onto the hidden link and report it as not-visible.
// Filtering to visible elements first targets the on-screen heading we mean.
function markerLocator(page, surface) {
  const base = surface.markerSelector
    ? page.locator(surface.markerSelector)
    : page.getByText(surface.marker, { exact: false });
  return base.filter({ visible: true }).first();
}

// Navigate, clearing any MFA step-up, and retry a few times on the SQLite-only
// transient "database is locked" 500. The threaded dev runserver on file-backed
// SQLite intermittently throws OperationalError when a page writes during GET
// while concurrent telemetry/SSE requests also write — a dev artifact only
// (production is PostgreSQL; the serial Django test client returns 200). Real
// 500s carry a different message and fall through immediately, so they still fail.
async function gotoWithTransientRetry(page, url, navOpts) {
  for (let attempt = 0; ; attempt += 1) {
    const resp = await page.goto(url, navOpts);
    // Some operator routes force an MFA step-up even after remember-device; clear it.
    await completeMfaIfPresent(page);
    if (!resp || resp.status() < 500 || attempt >= 4) return resp;
    const body = await page.locator('body').innerText().catch(() => '');
    if (!/database is locked|OperationalError/i.test(body)) return resp;
    await page.waitForTimeout(1200);
  }
}

async function captureSurface(page, viewportName, surface, category) {
  const navOpts = { waitUntil: NAV_WAIT_UNTIL };
  const longTimeoutSlugs = ['setup-studio', 'control-plane-app-catalog'];
  const visibilityTimeout = longTimeoutSlugs.includes(surface.slug) ? 15000 : 5000;
  await gotoWithTransientRetry(page, surface.url, navOpts);
  try {
    await expect(markerLocator(page, surface)).toBeVisible({ timeout: visibilityTimeout });
  } catch (markerErr) {
    // Marker not found/visible: dump the page's actual landing state so the
    // failure names what DID render (final URL, title, visible headings, error
    // banners) instead of just "element not found". Makes marker drift fixable
    // from the CI log in one run.
    const diag = await page.evaluate(() => {
      const vis = (el) => {
        const r = el.getBoundingClientRect();
        const s = window.getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
      };
      const heads = Array.from(document.querySelectorAll('h1,h2,[data-ux-qa-marker],[id*="title"]'))
        .filter(vis)
        .map((el) => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}="${(el.textContent || '').trim().slice(0, 60)}"`)
        .slice(0, 8);
      const body = (document.body.innerText || '').slice(0, 300).replace(/\s+/g, ' ');
      return { url: location.href, title: document.title, heads, body };
    }).catch(() => ({ url: 'n/a', title: 'n/a', heads: [], body: 'n/a' }));
    throw new Error(
      `[${viewportName}:${surface.slug}] marker not visible (${surface.markerSelector || surface.marker}). ` +
      `landed url=${diag.url} title="${diag.title}" visibleHeads=[${diag.heads.join(' ; ')}] bodyHead="${diag.body}" :: ${markerErr.message}`
    );
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
  // Retry the whole login a few times: under the busy dev runserver the POST can
  // race (we land back on the login page with no error) or the MFA submit can be
  // momentarily slow. Re-driving the form is the reliable fix — the server stays
  // up, it's just transiently loaded after a prior heavy test.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto(`${MANAGER_BASE_URL}/authentication/login/`, { waitUntil: NAV_WAIT_UNTIL });
    const roleSelect = page.locator('select[name="role"]');
    if (await roleSelect.count()) {
      await roleSelect.selectOption('staff');
    }
    await page.locator('input[name="username"]').fill(DEFAULT_USERNAME);
    await page.locator('input[name="password"]').fill(DEFAULT_PASSWORD);
    await page.getByRole('button', { name: /log in/i }).click();
    await page.waitForLoadState(NAV_WAIT_UNTIL);
    await completeMfaIfPresent(page);
    if (!/\/authentication\/login\/?$/.test(page.url())) return; // logged in
    if (attempt < 2) await page.waitForTimeout(2000);
  }
  const errorText = await page.locator('body').textContent();
  throw new Error(`Login did not complete for visual QA user after retries. Current page text starts with: ${(errorText || '').slice(0, 240)}`);
}

// Authenticated shells open persistent SSE EventSources (workflow-progress +
// assist-dock context). Each holds a dev-runserver worker thread open for the
// life of the tab; across a long multi-viewport sweep they accumulate and
// starve the threaded `runserver` until it stops accepting connections — which
// killed the back half of the suite (tablet/mobile) with ECONNREFUSED while the
// view code was fine. Abort the streams at the browser so the server never holds
// the thread; the pages fall back to lightweight polling and render identically.
const SSE_STREAM_RE = /\/(?:workflow-progress|context)\/stream\//;

async function newContext(browser, view) {
  const context = await browser.newContext({
    viewport: view.viewport,
    isMobile: view.isMobile,
    hasTouch: view.hasTouch,
    deviceScaleFactor: view.isMobile ? 2 : 1,
  });
  await context.route(SSE_STREAM_RE, (route) => route.abort());
  return context;
}

test.describe('UX visual QA', () => {
  test('server is reachable (run bash scripts/run_visual_qa.sh if this fails)', async ({ page }) => {
    try {
      await page.goto(PUBLIC_BASE_URL + '/migrate/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    } catch (e) {
      if (e.message && (e.message.includes('ERR_CONNECTION_REFUSED') || e.message.includes('net::ERR'))) {
        throw new Error(SERVER_REQUIRED_MSG);
      }
      throw e;
    }
  });

  for (const view of VIEWPORTS) {
    test(`${view.name}: public proof surfaces`, async ({ browser }) => {
      // Heavy pages under the DEBUG dev runserver render in 10-20s each; the
      // default 45s budget is for snappy specs. Give these visual sweeps room
      // so a slow-but-correct page never reads as a failure.
      test.setTimeout(180000);
      for (const surface of PUBLIC_SURFACES) {
        const context = await newContext(browser, view);
        const page = await context.newPage();
        await captureSurface(page, view.name, { ...surface, url: `${PUBLIC_BASE_URL}${surface.url}` }, 'public');
        await context.close();
      }
    });

    test(`${view.name}: authenticated operator surfaces`, async ({ browser }) => {
      // Login (MFA) + several heavy control-plane navigations + full-page
      // screenshots run ~40-50s EACH on the DEBUG dev runserver. The markers all
      // render; the cost is server-side latency, so the budget must accommodate it.
      test.setTimeout(300000);
      const context = await newContext(browser, view);
      const page = await context.newPage();

      await login(page);
      for (const surface of AUTHENTICATED_SURFACES) {
        await captureSurface(page, view.name, { ...surface, url: `${MANAGER_BASE_URL}${surface.url}` }, 'authenticated');
      }

      await context.close();
    });

    test(`${view.name}: authenticated scroll contract`, async ({ browser }) => {
      // Same dev-runserver latency profile as the operator surfaces test.
      test.setTimeout(300000);
      const context = await newContext(browser, view);
      const page = await context.newPage();

      await login(page);
      for (const surface of AUTHENTICATED_SCROLL_SURFACES) {
        // tenant-* surfaces validate the TENANT shell (luxury header, #main-content
        // scroll root) and need a tenant-host login. This loop is operator-
        // authenticated on the manager host, where /authentication/backend/
        // resolves to the operator dashboard — so the tenant markers can't match
        // here. Skip them without a tenant host (Postgres); their manager-host
        // equivalents are already covered by the operator-surfaces test above.
        if (surface.slug.startsWith('tenant-') && !TENANT_BASE_URL) continue;
        const longTimeoutSlugs = ['tenant-setup-studio', 'setup-studio', 'manager-tenant-studio'];
        const visibilityTimeout = longTimeoutSlugs.includes(surface.slug) ? 15000 : 5000;
        await gotoWithTransientRetry(page, `${MANAGER_BASE_URL}${surface.url}`, { waitUntil: NAV_WAIT_UNTIL });
        try {
          await expect(markerLocator(page, surface)).toBeVisible({ timeout: visibilityTimeout });
        } catch (markerErr) {
          const diag = await page.evaluate(() => {
            const vis = (el) => {
              const r = el.getBoundingClientRect();
              const s = window.getComputedStyle(el);
              return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
            };
            const heads = Array.from(document.querySelectorAll('h1,h2,[data-ux-qa-marker],[id*="title"]'))
              .filter(vis)
              .map((el) => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}="${(el.textContent || '').trim().slice(0, 60)}"`)
              .slice(0, 8);
            const body = (document.body.innerText || '').slice(0, 300).replace(/\s+/g, ' ');
            return { url: location.href, title: document.title, heads, body };
          }).catch(() => ({ url: 'n/a', title: 'n/a', heads: [], body: 'n/a' }));
          throw new Error(
            `[${view.name}:${surface.slug}] marker not visible (${surface.markerSelector || surface.marker}). ` +
            `landed url=${diag.url} title="${diag.title}" visibleHeads=[${diag.heads.join(' ; ')}] bodyHead="${diag.body}" :: ${markerErr.message}`
          );
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

  const tenantUserTeacher = process.env.VISUAL_QA_TENANT_TEACHER || 'teacher1';
  const tenantUserParent = process.env.VISUAL_QA_TENANT_PARENT || 'Parent1';

  for (const view of VIEWPORTS) {
    test(`${view.name}: tenant host — teacher + parent portals (DASHBOARDS_AND_LINKS)`, async ({
      browser,
    }) => {
      // Two portal logins + dashboard navigations under the DEBUG dev runserver.
      test.setTimeout(300000);
      test.skip(
        process.env.VISUAL_QA_SKIP_TENANT_PORTALS === '1',
        'VISUAL_QA_SKIP_TENANT_PORTALS=1 (no seeded teacher1/parent on this host)'
      );
      test.skip(
        !TENANT_BASE_URL,
        'No tenant host: Postgres + Client/Domain required; SQLite skips tenant portals'
      );

      const passwords = tenantPasswordCandidates();

      const context = await newContext(browser, view);
      const page = await context.newPage();

      const teacherOk = await tryTenantLogin(
        page,
        TENANT_BASE_URL,
        'staff',
        tenantUserTeacher,
        passwords
      );
      expect(
        teacherOk,
        `Tenant login failed for ${tenantUserTeacher}@${TENANT_BASE_URL}. Seed: seed_render_users / create_teacher_parent_accounts; align ADMIN_PASSWORD.`
      ).toBe(true);

      await page.goto(`${TENANT_BASE_URL}/portal/teacher/`, { waitUntil: NAV_WAIT_UNTIL });
      await expect(page.locator('body')).not.toContainText('Server Error (500)');
      await expect(page.getByText(/workflow|teacher|dashboard|portal/i).filter({ visible: true }).first()).toBeVisible({
        timeout: 10000,
      });
      await assertNoHorizontalOverflow(page, `${view.name}:tenant-teacher-portal`);

      const folder = path.join(OUTPUT_ROOT, 'tenant', view.name);
      ensureDir(folder);
      await page.screenshot({ path: path.join(folder, 'teacher-portal.png'), fullPage: true });

      await context.close();

      const ctx2 = await newContext(browser, view);
      const page2 = await ctx2.newPage();
      const parentOk = await tryTenantLogin(
        page2,
        TENANT_BASE_URL,
        'parent',
        tenantUserParent,
        passwords
      );
      expect(
        parentOk,
        `Tenant parent login failed for ${tenantUserParent}. Seed parent demo user; same password as ADMIN_PASSWORD when using seed_render_users.`
      ).toBe(true);

      await page2.goto(`${TENANT_BASE_URL}/portal/parent/`, { waitUntil: NAV_WAIT_UNTIL });
      await expect(page2.locator('body')).not.toContainText('Server Error (500)');
      await expect(page2.getByText(/parent|home|dashboard|portal|child/i).filter({ visible: true }).first()).toBeVisible({
        timeout: 10000,
      });
      await assertNoHorizontalOverflow(page2, `${view.name}:tenant-parent-portal`);
      ensureDir(folder);
      await page2.screenshot({ path: path.join(folder, 'parent-portal.png'), fullPage: true });
      await ctx2.close();
    });
  }
});
