// @ts-check
/**
 * Control-plane layout audit (world-map leak / overlap regression guard).
 *
 * Loads the live /super/ control plane ONCE as an authenticated operator and,
 * at several desktop widths (looped in-page to spare the single-thread dev
 * server), measures the REAL cockpit sections that render on this surface
 * (rmc-cockpit-* chrome + lx-world map). Asserts:
 *   1. No horizontal leak — document does not scroll sideways; no in-flow
 *      section spills past the viewport edge.
 *   2. World map is BOUNDED — the SVG never balloons past its cell (the bug),
 *      and the cell respects its max-height.
 *   3. Nothing covers anything — no two IN-FLOW sections overlap in both axes.
 *      Intentional overlays (position fixed/absolute/sticky, e.g. the copilot
 *      rail and operator-tools tray) are excluded from the covering check.
 *
 * Run (manager-chromium project supplies host rules + storageState):
 *   npx playwright test control-plane-layout-audit --project=manager-chromium --workers=1
 */
const { test, expect } = require('@playwright/test');
const { ensureManagerSession, MANAGER_BASE_URL } = require('./helpers/manager-login');

const SUPER_URL = `${MANAGER_BASE_URL.replace(/\/$/, '')}/super/`;
const WIDTHS = [1280, 1440, 1680, 1920];
const EPS = 2;

// Real section-level containers on /super/ (curated from the rendered DOM).
const SECTIONS = [
  '.rmc-cockpit-workspace',
  '.rmc-cockpit-pulse',
  '.rmc-cockpit-ticker',
  '.lx-world',
  '.lx-notebook',
  '.lx-copilot',
];

function auditFn({ SECTIONS, EPS, width }) {
  const vw = document.documentElement.clientWidth;
  const out = { width, vw, sections: [], violations: [], map: null };

  const collect = (sel) => {
    // Top-most element of each selector (avoid nested duplicates).
    const els = Array.from(document.querySelectorAll(sel)).filter((el) => {
      return !el.parentElement || !el.parentElement.closest(sel);
    });
    return els.map((el, i) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return {
        key: els.length > 1 ? `${sel}#${i}` : sel,
        x: r.left, y: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height,
        pos: cs.position,
        vis: cs.visibility !== 'hidden' && cs.display !== 'none' && r.width > 0 && r.height > 0,
      };
    });
  };

  let boxes = [];
  for (const sel of SECTIONS) boxes = boxes.concat(collect(sel));
  boxes = boxes.filter((b) => b.vis);
  out.sections = boxes.map((b) => ({ key: b.key, pos: b.pos, w: +b.w.toFixed(0), h: +b.h.toFixed(0), x: +b.x.toFixed(0), r: +b.r.toFixed(0) }));

  // 1. Horizontal leak (document + each in-flow section within viewport).
  const scrollW = document.documentElement.scrollWidth;
  if (scrollW > vw + EPS) out.violations.push(`H-LEAK: scrollWidth ${scrollW} > vw ${vw}`);
  for (const b of boxes) {
    const overlay = b.pos === 'fixed' || b.pos === 'sticky' || b.pos === 'absolute';
    if (overlay) continue; // overlays may be offscreen/docked by design
    if (b.r > vw + EPS) out.violations.push(`H-OVERFLOW: '${b.key}' right=${b.r.toFixed(0)} > vw=${vw}`);
    if (b.x < -EPS) out.violations.push(`H-OVERFLOW: '${b.key}' left=${b.x.toFixed(0)} < 0`);
  }

  // 2. World map bounded.
  const mapCell = document.querySelector('.lx-world__map');
  const mapSvg = document.querySelector('.lx-world__svg');
  if (mapCell && mapSvg) {
    const c = mapCell.getBoundingClientRect();
    const s = mapSvg.getBoundingClientRect();
    out.map = { cellH: +c.height.toFixed(1), svgH: +s.height.toFixed(1), svgBottom: +s.bottom.toFixed(1), cellBottom: +c.bottom.toFixed(1) };
    if (s.height > c.height + 4) out.violations.push(`MAP-BALLOON: svg h=${s.height.toFixed(0)} > cell h=${c.height.toFixed(0)}`);
    if (s.bottom > c.bottom + 4) out.violations.push(`MAP-SPILL: svg bottom=${s.bottom.toFixed(0)} > cell bottom=${c.bottom.toFixed(0)}`);
    if (c.height > 340) out.violations.push(`MAP-TALL: cell h=${c.height.toFixed(0)} > 340 cap`);
  }

  // 3. No covering — pairwise overlap among IN-FLOW sections only (skip overlays).
  const inflow = boxes.filter((b) => !(b.pos === 'fixed' || b.pos === 'sticky' || b.pos === 'absolute'));
  for (let i = 0; i < inflow.length; i++) {
    for (let j = i + 1; j < inflow.length; j++) {
      const a = inflow[i], b = inflow[j];
      const ox = Math.min(a.r, b.r) - Math.max(a.x, b.x);
      const oy = Math.min(a.b, b.b) - Math.max(a.y, b.y);
      if (ox > EPS && oy > EPS) {
        const aInB = a.x >= b.x - EPS && a.r <= b.r + EPS && a.y >= b.y - EPS && a.b <= b.b + EPS;
        const bInA = b.x >= a.x - EPS && b.r <= a.r + EPS && b.y >= a.y - EPS && b.b <= a.b + EPS;
        if (!aInB && !bInA) out.violations.push(`COVER: '${a.key}' overlaps '${b.key}' by ${ox.toFixed(0)}x${oy.toFixed(0)}px`);
      }
    }
  }
  return out;
}

test('control plane: bounded map, no overflow, no covering across widths', async ({ page }) => {
  test.setTimeout(180000);

  await ensureManagerSession(page);
  await page.goto(SUPER_URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.locator('.rmc-cockpit-page, #cp-main-content, #content, .lx-world').first().waitFor({ state: 'visible', timeout: 90000 });

  const allViolations = [];
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 1000 });
    await page.waitForTimeout(400);
    if (width === 1440 || width === 1920) {
      await page.screenshot({ path: `artifacts/cp-super-${width}.png`, fullPage: true }).catch(() => {});
    }
    const report = await page.evaluate(auditFn, { SECTIONS, EPS, width });
    // eslint-disable-next-line no-console
    console.log(`[layout ${width}] sections=${report.sections.map((s) => `${s.key}(${s.pos} ${s.w}x${s.h})`).join(' | ')}`);
    // eslint-disable-next-line no-console
    console.log(`[layout ${width}] map=${JSON.stringify(report.map)} violations=${report.violations.length}`);
    for (const v of report.violations) {
      // eslint-disable-next-line no-console
      console.log(`[layout ${width}]   x ${v}`);
      allViolations.push(`@${width}: ${v}`);
    }
  }

  expect(allViolations, 'layout violations across widths').toEqual([]);
});
