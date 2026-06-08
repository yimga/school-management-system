// @ts-check
/**
 * Control-plane layout audit (world-map leak / overlap regression guard).
 *
 * Loads each control-plane surface ONCE as an authenticated operator and, at a
 * range of widths (narrow → ultrawide, looped in-page to spare the single-thread
 * dev server), measures the REAL cockpit sections that render. Asserts:
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

const BASE = MANAGER_BASE_URL.replace(/\/$/, '');
const SURFACES = [
  { name: 'landing', path: '/super/' },
  { name: 'founder', path: '/super/founder/' },
  { name: 'command-center', path: '/super/command-center/' },
];
const WIDTHS = [768, 1024, 1280, 1440, 1680, 1920];
const EPS = 2;

const SECTIONS = [
  '.rmc-cockpit-workspace',
  '.rmc-cockpit-pulse',
  '.rmc-cockpit-ticker',
  '.lx-world',
  '.lx-notebook',
  '.lx-copilot',
  '.lx-slo',
  '.lx-forecast',
  '.lx-heatmap',
  '.lx-trust',
  '.lx-waterfall',
  '.lx-audit',
];

function auditFn({ SECTIONS, EPS, width }) {
  const vw = document.documentElement.clientWidth;
  const out = { width, vw, sections: [], violations: [], map: null };
  // Effective on-screen rect: clip the element to every ancestor that clips
  // overflow. A section inside a collapsed/clipped <details> (overflow:hidden,
  // 2px tall) is NOT visible at its full bounding rect — measuring the unclipped
  // rect produces phantom "overlaps". Clip so we only ever reason about pixels
  // the user can actually see.
  const clippedRect = (el) => {
    const r = el.getBoundingClientRect();
    let x = r.left, y = r.top, rr = r.right, bb = r.bottom;
    let p = el.parentElement;
    while (p) {
      const cs = getComputedStyle(p);
      const ov = `${cs.overflow}${cs.overflowX}${cs.overflowY}`;
      if (/(hidden|clip|auto|scroll)/.test(ov)) {
        const pr = p.getBoundingClientRect();
        x = Math.max(x, pr.left); y = Math.max(y, pr.top);
        rr = Math.min(rr, pr.right); bb = Math.min(bb, pr.bottom);
      }
      p = p.parentElement;
    }
    return { x, y, r: rr, b: bb, w: rr - x, h: bb - y };
  };
  const collect = (sel) => {
    const els = Array.from(document.querySelectorAll(sel)).filter(
      (el) => !el.parentElement || !el.parentElement.closest(sel)
    );
    return els.map((el, i) => {
      const c = clippedRect(el);
      const cs = getComputedStyle(el);
      return {
        key: els.length > 1 ? `${sel}#${i}` : sel,
        x: c.x, y: c.y, r: c.r, b: c.b, w: c.w, h: c.h,
        pos: cs.position,
        vis: cs.visibility !== 'hidden' && cs.display !== 'none' && c.w > EPS && c.h > EPS,
      };
    });
  };
  let boxes = [];
  for (const sel of SECTIONS) boxes = boxes.concat(collect(sel));
  boxes = boxes.filter((b) => b.vis);
  out.sections = boxes.map((b) => ({ key: b.key, pos: b.pos, w: +b.w.toFixed(0), h: +b.h.toFixed(0) }));

  const scrollW = document.documentElement.scrollWidth;
  if (scrollW > vw + EPS) out.violations.push(`H-LEAK: scrollWidth ${scrollW} > vw ${vw}`);
  for (const b of boxes) {
    if (b.pos === 'fixed' || b.pos === 'sticky' || b.pos === 'absolute') continue;
    if (b.r > vw + EPS) out.violations.push(`H-OVERFLOW: '${b.key}' right=${b.r.toFixed(0)} > vw=${vw}`);
    if (b.x < -EPS) out.violations.push(`H-OVERFLOW: '${b.key}' left=${b.x.toFixed(0)} < 0`);
  }

  const mapCell = document.querySelector('.lx-world__map');
  const mapSvg = document.querySelector('.lx-world__svg-fallback');
  const mapGlobe = document.querySelector('.lx-world__globe');
  if (mapCell && (mapSvg || mapGlobe)) {
    const c = mapCell.getBoundingClientRect();
    const vis = mapGlobe || mapSvg;
    const s = vis.getBoundingClientRect();
    out.map = { cellH: +c.height.toFixed(1), svgH: +s.height.toFixed(1) };
    if (s.height > c.height + 4) out.violations.push(`MAP-BALLOON: map h=${s.height.toFixed(0)} > cell h=${c.height.toFixed(0)}`);
    if (s.bottom > c.bottom + 4) out.violations.push(`MAP-SPILL: map bottom=${s.bottom.toFixed(0)} > cell bottom=${c.bottom.toFixed(0)}`);
    if (c.height > 340) out.violations.push(`MAP-TALL: cell h=${c.height.toFixed(0)} > 340 cap`);
  }

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

for (const surface of SURFACES) {
  test(`control plane [${surface.name}]: bounded map, no overflow, no covering`, async ({ page }) => {
    test.setTimeout(200000);
    await ensureManagerSession(page);
    const resp = await page.goto(BASE + surface.path, { waitUntil: 'domcontentloaded', timeout: 90000 });
    // Surface may not exist on this build — skip cleanly rather than false-fail.
    if (resp && resp.status() >= 400) {
      test.skip(true, `${surface.path} returned HTTP ${resp.status()}`);
      return;
    }
    await page.locator('.rmc-cockpit-page, #cp-main-content, #content, .lx-world').first().waitFor({ state: 'visible', timeout: 90000 });
    // Measure each surface in its REAL user-default state — do NOT force-open
    // collapsibles. Force-expanding every <details> at once produces overlaps a
    // user never sees (each section is its own block and reflows on real expand);
    // that is a measurement artifact, not a layout bug.

    const allViolations = [];
    let sawAnySection = false;
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 1000 });
      await page.waitForTimeout(350);
      const report = await page.evaluate(auditFn, { SECTIONS, EPS, width });
      if (report.sections.length) sawAnySection = true;
      // eslint-disable-next-line no-console
      console.log(`[${surface.name} ${width}] sections=${report.sections.map((s) => `${s.key.replace(/^\./, '')}(${s.w}x${s.h})`).join(' ')} map=${JSON.stringify(report.map)} viol=${report.violations.length}`);
      for (const v of report.violations) {
        // eslint-disable-next-line no-console
        console.log(`[${surface.name} ${width}]   x ${v}`);
        allViolations.push(`[${surface.name}@${width}] ${v}`);
      }
    }
    // Surfaces with their own non-cockpit layout (e.g. command-center "Mission
    // Queues") legitimately render no cockpit sections — skip rather than fail.
    if (!sawAnySection) {
      test.skip(true, `${surface.name}: no cockpit sections on this surface (different layout)`);
      return;
    }
    expect(allViolations, `layout violations on ${surface.name}`).toEqual([]);
  });
}
