// Render the faithful control-plane reproduction in real Chrome and measure the
// copilot rail's actual geometry. Proves whether it docks as a vertical strip on
// the right (grid column 3) or collapses to a horizontal bottom band.
import { chromium } from 'playwright';
import { pathToFileURL } from 'url';
import path from 'path';

const HTML = path.resolve('var/copilot-proof/copilot_rail_proof.html');
const url = pathToFileURL(HTML).href;

async function measure(page) {
  return await page.evaluate(() => {
    const shell = document.querySelector('.rmc-app-shell');
    const aside = document.querySelector('.rmc-app-shell__copilot');
    const r = aside.getBoundingClientRect();
    const cs = getComputedStyle(aside);
    const shellCS = getComputedStyle(shell);
    return {
      x: Math.round(r.x), y: Math.round(r.y),
      w: Math.round(r.width), h: Math.round(r.height),
      right: Math.round(r.right),
      vw: window.innerWidth, vh: window.innerHeight,
      gridColumn: cs.gridColumn,
      position: cs.position,
      display: aside.offsetParent === null && cs.display === 'none' ? 'none' : cs.display,
      shellDisplay: shellCS.display,
      shellCols: shellCS.gridTemplateColumns,
    };
  });
}

function verdict(m) {
  // A correct right-dock: tall (h>w), narrow, flush to the right viewport edge,
  // and starts below the header (y>0). A bottom band would be wide (w>h) and full-width.
  if (m.display === 'none') return { ok: true, note: 'hidden (responsive: <=1199px hides rail by design)' };
  const isVertical = m.h > m.w;
  const flushRight = Math.abs(m.right - m.vw) <= 6;
  const notFullWidth = m.w < m.vw * 0.6;
  const belowHeader = m.y > 0;
  const ok = isVertical && flushRight && notFullWidth && belowHeader;
  return {
    ok,
    note: `vertical=${isVertical} flushRight=${flushRight} notFullWidth=${notFullWidth} belowHeader=${belowHeader} gridColumn=${m.gridColumn}`,
  };
}

const widths = [1920, 1440, 1366];
const browser = await chromium.launch({ channel: 'chrome', headless: true });
let allPass = true;

for (const width of widths) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(url, { waitUntil: 'load' });
  // Kill the 420ms grid-template-columns transition (rmc-cp-200x.css:32) so we
  // measure the SETTLED layout, not an intermediate animation frame.
  await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;animation:none!important}' });
  await page.waitForTimeout(150);

  console.log(`\n================ viewport ${width}x900 ================`);

  // Collapsed
  await page.evaluate(() => document.querySelector('.rmc-app-shell').setAttribute('data-copilot', 'collapsed'));
  await page.waitForTimeout(120);
  let m = await measure(page);
  let v = verdict(m);
  console.log(`[collapsed]  ${JSON.stringify(m)}`);
  console.log(`             ${v.ok ? 'PASS' : 'FAIL'} — ${v.note}`);
  if (width > 1199 && !v.ok) allPass = false;
  if (width === 1920) await page.screenshot({ path: 'var/copilot-proof/shot_collapsed_1920.png' });

  // Expanded
  await page.evaluate(() => document.querySelector('.rmc-app-shell').setAttribute('data-copilot', 'expanded'));
  await page.waitForTimeout(120);
  m = await measure(page);
  v = verdict(m);
  console.log(`[expanded]   ${JSON.stringify(m)}`);
  console.log(`             ${v.ok ? 'PASS' : 'FAIL'} — ${v.note}`);
  if (width > 1199 && !v.ok) allPass = false;
  if (width === 1920) await page.screenshot({ path: 'var/copilot-proof/shot_expanded_1920.png' });

  // Drop the attribute — proves the :has() fallback alone still right-docks
  await page.evaluate(() => {
    const s = document.querySelector('.rmc-app-shell');
    s.setAttribute('data-copilot', 'collapsed');
    s.removeAttribute('data-rmc-app-shell-copilot');
  });
  await page.waitForTimeout(120);
  m = await measure(page);
  v = verdict(m);
  console.log(`[no-attr]    ${JSON.stringify(m)}`);
  console.log(`             ${v.ok ? 'PASS' : 'FAIL'} — ${v.note} (:has fallback)`);
  if (width > 1199 && !v.ok) allPass = false;

  await page.close();
}

await browser.close();
console.log(`\n================ RESULT: ${allPass ? 'ALL PASS ✅' : 'FAIL ❌'} ================`);
process.exit(allPass ? 0 : 1);
