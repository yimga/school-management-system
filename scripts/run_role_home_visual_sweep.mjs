#!/usr/bin/env node
/**
 * Focused abrupt-end sweep: parent / teacher / student / admin / marketing threshold-era.
 * Uses tests/e2e/helpers/tenant-login.js (path-tenant 127.0.0.1 + MFA TOTP) — batch 1701 harness.
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';

const PORT = process.env.VISUAL_QA_PORT || '8012';
process.env.VISUAL_QA_PORT = PORT;

const require = createRequire(import.meta.url);
const { loginTenant, TENANT_BASE_URL } = require('../tests/e2e/helpers/tenant-login.js');

const MKT_HOST = process.env.MARKETING_SWEEP_HOST || 'runmycampus.com';
const MKT_BASE = process.env.MARKETING_SWEEP_BASE || `http://127.0.0.1:${PORT}`;
const TENANT_ONLY = process.env.ROLE_SWEEP_TENANT_ONLY === '1';
const OUT = path.join(process.cwd(), 'var/role-home-visual-sweep.json');

function sweepPageInBrowser(scrollRootSel) {
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
  const roots = scrollRootSel
    ? [document.querySelector(scrollRootSel)]
    : [
        document.querySelector('#main-content'),
        document.querySelector('main'),
        document.querySelector('.rmc-app-shell__canvas-body'),
      ];
  const main = findScrollable(roots.find(Boolean) || null);
  const body = document.body;
  const bodyOY = body ? getComputedStyle(body).overflowY : '';
  const canScroll = !!(main && main.scrollHeight > main.clientHeight + 2);
  if (canScroll) {
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
  return {
    path: location.pathname,
    title: document.title,
    armed: document.documentElement.getAttribute('data-rmc-reveal-armed'),
    revealTotal: document.querySelectorAll('.rmc-reveal').length,
    strandedAfter,
    failures,
    ok: failures.length === 0,
    canScroll,
  };
}

const DEMO_PREFIX = process.env.TENANT_DEMO_USERNAME_PREFIX || 'demo';
const DEMO_PASS = process.env.TENANT_SWEEP_PASSWORD || 'Test1234';

const SURFACES = [
  {
    label: 'parent-home',
    url: '/portal/parent/',
    user: `${DEMO_PREFIX}.parent`,
    pass: DEMO_PASS,
  },
  {
    label: 'teacher-home',
    url: '/portal/teacher/',
    user: `${DEMO_PREFIX}.teacher`,
    pass: DEMO_PASS,
  },
  {
    label: 'student-grades',
    url: '/portal/student-portal/grades/',
    user: `${DEMO_PREFIX}.student`,
    pass: DEMO_PASS,
  },
  {
    label: 'admin-backend',
    url: '/authentication/backend/',
    user: `${DEMO_PREFIX}.admin`,
    pass: DEMO_PASS,
  },
  {
    label: 'admin-performance',
    url: '/authentication/backend/performance/',
    user: `${DEMO_PREFIX}.admin`,
    pass: DEMO_PASS,
  },
];

if (!TENANT_ONLY) {
  SURFACES.push(
    {
      label: 'marketing-threshold',
      url: '/experience/threshold-era/',
      base: MKT_BASE,
      host: MKT_HOST,
      anon: true,
      scrollRoot: 'main',
    },
    {
      label: 'marketing-home',
      url: '/',
      base: MKT_BASE,
      host: MKT_HOST,
      anon: true,
      scrollRoot: 'main',
    },
  );
}

const browser = await chromium.launch({ headless: true });
const results = [];

for (const s of SURFACES) {
  const base = s.base || TENANT_BASE_URL;
  const ctxOpts = {
    baseURL: base,
    viewport: { width: 1400, height: 900 },
  };
  if (s.host) {
    ctxOpts.extraHTTPHeaders = { Host: s.host };
  }
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  const row = { label: s.label, requested: s.url, base, host: s.host || null };
  try {
    if (!s.anon) {
      await loginTenant(page, { username: s.user, password: s.pass });
      row.loginPath = new URL(page.url()).pathname;
    }
    const response = await page.goto(s.url, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    row.httpStatus = response ? response.status() : null;
    if (row.httpStatus && row.httpStatus >= 400) {
      row.failures = [`http_${row.httpStatus}`];
      row.ok = false;
      results.push(row);
      await ctx.close();
      continue;
    }
    const title = await page.title();
    if (/page not found|404|not found at/i.test(title)) {
      row.failures = ['page_not_found'];
      row.ok = false;
      results.push(row);
      await ctx.close();
      continue;
    }
    await page.waitForTimeout(1200);
    const scrollRoot = s.scrollRoot || '#main-content';
    let audit = await page.evaluate(sweepPageInBrowser, scrollRoot);
    await page.waitForTimeout(500);
    audit = await page.evaluate(sweepPageInBrowser, scrollRoot);
    Object.assign(row, audit);
    if (s.label === 'marketing-threshold') {
      row.marketing = await page.evaluate(() => ({
        ascGate: !!document.querySelector('.mkt-asc-gate'),
        ascDay: !!document.querySelector('.mkt-asc-day'),
        trustNav: !!document.querySelector('.mkt-rev-trust-nav'),
        parentCard: !!document.querySelector('.mkt-asc-parent-card'),
      }));
      if (!row.marketing.ascGate || !row.marketing.trustNav) {
        row.failures = [...(row.failures || []), 'marketing_content_missing'];
        row.ok = false;
      }
    }
    if (s.label === 'marketing-home') {
      row.marketing = await page.evaluate(() => ({
        oneRecordScroll: !!document.querySelector('[data-mkt-one-record-scroll]'),
        chapters: document.querySelectorAll('.mkt-or__chapter').length,
        stagePanels: document.querySelectorAll('.mkt-or__panel').length,
      }));
      if (!row.marketing.oneRecordScroll || row.marketing.chapters < 6 || row.marketing.stagePanels < 6) {
        row.failures = [...(row.failures || []), 'one_record_scroll_missing'];
        row.ok = false;
      }
    }
  } catch (e) {
    row.ok = false;
    row.failures = ['exception'];
    row.error = String(e).slice(0, 300);
  }
  results.push(row);
  await ctx.close();
}
await browser.close();

const payload = {
  generatedAt: new Date().toISOString(),
  tenantBase: TENANT_BASE_URL,
  marketingBase: MKT_BASE,
  marketingHost: MKT_HOST,
  tenantOnly: TENANT_ONLY,
  passed: results.filter((r) => r.ok !== false).length,
  failed: results.filter((r) => r.ok === false).length,
  results,
};
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(payload, null, 2) + '\n');
console.log(JSON.stringify(payload, null, 2));
process.exit(payload.failed ? 1 : 0);
