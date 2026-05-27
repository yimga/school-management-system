#!/usr/bin/env node
/**
 * Browser gate for manager backoffice scroll roots.
 *
 * Requires a running Django server and manager auth credentials. Defaults match
 * scripts/seed_manager_playwright_auth.js.
 */

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { loginManager, MANAGER_BASE_URL } = require('../tests/e2e/helpers/manager-login');

const OUT = path.join(process.cwd(), 'docs/generated/backoffice_scroll_browser_validation.json');
const MANAGER_HOST = process.env.VISUAL_QA_MANAGER_HOST || new URL(baseUrl()).hostname;

const ROUTES = [
  {
    path: '/admin/accounts/user/',
    label: 'manager-admin-users',
    scroller: '#cp-main-content',
    forbiddenScroller: '.rmc-app-shell__canvas',
    marker: 'data-rmc-backoffice-scroll-root="main"',
    cacheBust: false,
  },
  {
    path: '/super/platform-operator-hub/',
    label: 'manager-super-operator-hub',
    scroller: '.rmc-app-shell__canvas-body',
    forbiddenScroller: '.rmc-app-shell__canvas',
    marker: 'data-shell-main="control-plane"',
  },
];

function baseUrl() {
  return MANAGER_BASE_URL.replace(/\/$/, '');
}

async function inspectRoute(page, route) {
  const joiner = route.path.includes('?') ? '&' : '?';
  const url = route.cacheBust === false
    ? `${baseUrl()}${route.path}`
    : `${baseUrl()}${route.path}${joiner}scroll_audit=${Date.now()}`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.locator(route.scroller).first().waitFor({ state: 'attached', timeout: 30000 });
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});

  return await page.evaluate(({ route }) => {
    const scroller = document.querySelector(route.scroller);
    const forbidden = document.querySelector(route.forbiddenScroller);
    const html = document.documentElement.outerHTML;
    const spacer = document.createElement('div');
    spacer.dataset.backofficeScrollProbe = '1';
    spacer.style.height = '1800px';
    spacer.style.minHeight = '1800px';
    spacer.style.opacity = '0';
    spacer.style.pointerEvents = 'none';
    spacer.style.flex = '0 0 auto';
    scroller.appendChild(spacer);
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    const after = scroller.scrollTop;
    const style = getComputedStyle(scroller);
    const forbiddenStyle = forbidden ? getComputedStyle(forbidden) : null;
    const doc = document.documentElement;
    const body = document.body;
    const row = {
      label: route.label,
      path: route.path,
      url: location.href,
      status: 'ok',
      markerPresent: html.includes(route.marker),
      scrollerSelector: route.scroller,
      scrollerClientHeight: scroller.clientHeight,
      scrollerScrollHeight: scroller.scrollHeight,
      scrollBefore: before,
      scrollAfter: after,
      overflowY: style.overflowY,
      scrollbarColor: style.scrollbarColor || '',
      scrollbarGutter: style.scrollbarGutter || '',
      forbiddenOverflowY: forbiddenStyle ? forbiddenStyle.overflowY : '',
      bodyOverflowY: getComputedStyle(body).overflowY,
      rootOverflowY: getComputedStyle(doc).overflowY,
      innerWidth: innerWidth,
      rootScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      hasHorizontalOverflow: doc.scrollWidth > innerWidth + 1 || body.scrollWidth > innerWidth + 1,
      failures: [],
    };
    spacer.remove();
    scroller.scrollTop = 0;

    if (!row.markerPresent) row.failures.push('missing_route_marker');
    if (!['auto', 'scroll'].includes(row.overflowY)) row.failures.push(`scroller_overflow_not_scrollable:${row.overflowY}`);
    if (row.scrollAfter < 200) row.failures.push(`scroll_did_not_move:${row.scrollAfter}`);
    if (/transparent\s+transparent/i.test(row.scrollbarColor)) row.failures.push('scrollbar_color_transparent');
    if (!/stable/i.test(row.scrollbarGutter)) row.failures.push(`scrollbar_gutter_not_stable:${row.scrollbarGutter}`);
    if (row.hasHorizontalOverflow) row.failures.push('horizontal_overflow');
    if ((route.label.includes('super') || route.label.includes('admin')) && row.forbiddenOverflowY !== 'hidden') {
      row.failures.push(`outer_canvas_not_hidden:${row.forbiddenOverflowY}`);
    }
    row.status = row.failures.length ? 'fail' : 'ok';
    return row;
  }, { route });
}

async function main() {
  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHROMIUM_CHANNEL || 'chromium',
    args: [
      process.env.PLAYWRIGHT_HOST_RULES
        ? `--host-resolver-rules=${process.env.PLAYWRIGHT_HOST_RULES}`
        : '--host-resolver-rules=MAP manager.runmycampus.com 127.0.0.1, MAP manager.localtest.me 127.0.0.1',
      '--proxy-server=direct://',
      '--proxy-bypass-list=*',
    ],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    serviceWorkers: 'block',
  });
  if (process.env.MANAGER_SESSIONID) {
    await context.addCookies([
      {
        name: 'rmc_manager_sessionid',
        value: process.env.MANAGER_SESSIONID,
        domain: MANAGER_HOST,
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
      },
      {
        name: 'sessionid',
        value: process.env.MANAGER_SESSIONID,
        domain: MANAGER_HOST,
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
  }
  const page = await context.newPage();
  if (!process.env.MANAGER_SESSIONID) {
    await loginManager(page);
  }

  const rows = [];
  for (const route of ROUTES) {
    rows.push(await inspectRoute(page, route));
  }
  await browser.close();

  const payload = {
    generatedAt: new Date().toISOString(),
    baseUrl: baseUrl(),
    ok: rows.every((row) => row.status === 'ok'),
    rows,
  };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, `${JSON.stringify(payload, null, 2)}\n`);
  console.log(JSON.stringify(payload, null, 2));
  if (!payload.ok) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
