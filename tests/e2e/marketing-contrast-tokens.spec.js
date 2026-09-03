// @ts-check
/**
 * Marketing colour-contrast regression — measured, not read.
 *
 * Every assertion here computes the WCAG 2.1 contrast ratio from the LIVE
 * rendered page: `getComputedStyle().color`, the composited effective
 * background of the ancestor chain, and the cumulative `opacity` applied
 * between the two. Nothing in this file looks at CSS source text, because a
 * test that greps a stylesheet stays green when the behaviour is deleted --
 * and because the cascade on this surface is 90+ stylesheets deep, so the rule
 * that wins is routinely not the rule that mentions the colour.
 *
 * The nine elements below are the ones the axe sweep
 * (scripts/run_marketing_axe_sweep.mjs) reported as `color-contrast`, impact
 * serious, across all 30 marketing page-views. Ratios recorded when this file
 * landed are in each case's comment.
 *
 * Requires a marketing host:
 *   MARKETING_BASE_URL=http://runmycampus.com:8010 \
 *     npx playwright test tests/e2e/marketing-contrast-tokens.spec.js \
 *       --project=marketing-chromium
 */
const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8010';

test.use({
  baseURL: MARKETING_BASE_URL,
  // Determinism: static/marketing/js/marketing-motion.js reveals every
  // [data-mkt-reveal] synchronously under reduced motion, so the DOM this
  // spec measures does not depend on where the IntersectionObserver got to.
  reducedMotion: 'reduce',
  viewport: { width: 1280, height: 900 },
});

/**
 * Injected into the page. Measures EVERY element matching `selector` and
 * returns them worst-ratio-first, or null when none are present.
 *
 * Every match, not the first: a de-emphasised list dims its INACTIVE items, so
 * `.first()` plus a scroll-into-view lands on the item the page has just made
 * active and reports the one reading that was never the problem.
 */
/* istanbul ignore next -- runs in the browser */
function measureContrastAll(selector) {
  const parse = (value) => {
    const raw = String(value);
    // Chromium serialises a resolved `color-mix(in srgb, ...)` as
    // `color(srgb 0.13 0.16 0.23)` — 0..1 channels, NOT rgb(). Missing this
    // form makes the walk skip an opaque backdrop and report the page
    // background instead, which invents a failure that is not on screen.
    const cm = raw.match(
      /color\(\s*srgb\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)(?:\s*\/\s*([\d.eE+-]+))?/i,
    );
    if (cm) {
      return [
        Number(cm[1]) * 255,
        Number(cm[2]) * 255,
        Number(cm[3]) * 255,
        cm[4] === undefined ? 1 : Number(cm[4]),
      ];
    }
    const m = raw.match(
      /rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+))?/i,
    );
    if (!m) return null;
    return [Number(m[1]), Number(m[2]), Number(m[3]), m[4] === undefined ? 1 : Number(m[4])];
  };
  const over = (fg, bg) => {
    const a = fg[3];
    return [
      fg[0] * a + bg[0] * (1 - a),
      fg[1] * a + bg[1] * (1 - a),
      fg[2] * a + bg[2] * (1 - a),
      1,
    ];
  };
  const lum = (rgb) => {
    const ch = rgb.slice(0, 3).map((v) => {
      const c = v / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  };

  const measureOne = (el) => {
    // Effective background: walk up compositing translucent layers until opaque.
    // Track the cumulative opacity applied to `el` relative to that backdrop —
    // an ancestor `opacity` dims the text against the backdrop below it, which
    // is exactly how a de-emphasised list item can fail contrast while its
    // declared colour looks fine.
    let bg = null;
    let alpha = 1;
    // Start at the element itself: a button paints its own fill BEHIND its own
    // label, so skipping it reports the page background and understates nothing
    // — it fabricates a failure.
    let node = el;
    const layers = [];
    while (node) {
      const cs = getComputedStyle(node);
      const c = parse(cs.backgroundColor);
      if (c && c[3] > 0) {
        layers.push(c);
        if (c[3] >= 1) break;
      }
      alpha *= Number(cs.opacity);
      node = node.parentElement;
    }
    bg = [255, 255, 255, 1];
    for (let i = layers.length - 1; i >= 0; i -= 1) bg = over(layers[i], bg);

    const cs = getComputedStyle(el);
    const declared = parse(cs.color);
    if (!declared) return null;
    let fg = over(declared, bg);
    fg = over([fg[0], fg[1], fg[2], alpha], bg);

    const l1 = lum(fg);
    const l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);

    const px = parseFloat(cs.fontSize);
    const weight = Number(cs.fontWeight) || 400;
    const isLarge = px >= 24 || (px >= 18.66 && weight >= 700);

    const hex = (rgb) =>
      `#${rgb
        .slice(0, 3)
        .map((v) => Math.round(v).toString(16).padStart(2, '0'))
        .join('')}`;

    return {
      ratio: Math.round(ratio * 100) / 100,
      required: isLarge ? 3 : 4.5,
      fg: hex(fg),
      bg: hex(bg),
      fontSize: px,
      fontWeight: weight,
      opacity: Math.round(alpha * 1000) / 1000,
    };
  };

  const nodes = [...document.querySelectorAll(selector)];
  if (!nodes.length) return null;
  const measured = nodes.map(measureOne).filter(Boolean);
  if (!measured.length) return null;
  measured.sort((a, b) => a.ratio - b.ratio);
  return { count: nodes.length, worst: measured[0] };
}

/**
 * Each case: the route, a selector for the element that used to fail, and the
 * ratio measured before the design-token fix landed.
 */
const CASES = [
  {
    route: '/',
    selector: '.mkt-navbar .rmc-brand-mark__title--platform .rmc-brand-word--gold',
    was: 1.96,
    why: 'brand gold #d4af37 as wordmark text on the editorial cream #FAF7F2',
  },
  {
    route: '/',
    selector: '.mkt-footer-seal__wordmark--platform .rmc-brand-word--gold',
    was: 1.96,
    why: 'same gold in the footer seal wordmark',
  },
  {
    route: '/',
    selector: '.mkt-v3-bell-clock__step:not(.is-active) .mkt-v3-bell-clock__label',
    was: 2.57,
    why: 'inactive bell-clock step de-emphasised with opacity: 0.55',
  },
  {
    route: '/',
    selector: '.mkt-v3-bell-clock__step:not(.is-active) .mkt-v3-bell-clock__time',
    was: 3.87,
    why: 'same opacity, inherited ink',
  },
  {
    route: '/',
    selector: '.mkt-v3-cinematic .mkt-edt-section-headline',
    was: 1.06,
    why: 'light-surface editorial ink on the inverted cinematic band #0C1422',
  },
  {
    route: '/',
    selector: '.mkt-v3-cinematic .mkt-edt-eyebrow',
    was: 2.86,
    why: 'same band, subtle ink',
  },
  {
    route: '/',
    selector: '.mkt-edt-plan--featured .mkt-edt-plan__cta',
    was: 2.03,
    why: 'generic marketing link colour #0645ad outranking the CTA on its dark pill',
  },
  {
    route: '/run/',
    selector: '.mkt-v3-cta',
    was: 3.47,
    why: 'flat dark CTA ink #1a1612 on the terracotta accent #C2410C',
  },
  {
    route: '/demo/',
    selector: '.mkt-personality-viz__metric-delta',
    was: 3.04,
    why: 'mid-tone personality accent used as text',
  },
  {
    route: '/developers/',
    selector: '.mkt-personality-viz__metric-label',
    was: 1.66,
    why: 'light-surface muted ink on the developers dark terminal band',
  },
  {
    route: '/pricing/',
    selector: 'button[data-mkt-consent-accept]',
    was: 3.19,
    why: 'white on the raw personality accent',
  },
  {
    route: '/platform/analytics/',
    selector: '.mkt-analytics-card--before h3',
    was: 1.52,
    why: 'a translucent "dark" card composited to a mid grey on the light marketing surface',
  },
  {
    route: '/platform/analytics/',
    selector: '.mkt-analytics-card li',
    was: 1.86,
    why: 'same card, list ink',
  },
  {
    route: '/platform/analytics/',
    selector: '.mkt-analytics-card--after h3',
    was: 1.6,
    why: 'same card, accent heading',
  },
  {
    route: '/platform/analytics/',
    selector: '.mkt-analytics-handoff-grid a',
    was: 1.35,
    why: 'the generic marketing link ink repainting an anchor that carries its own dark tile',
  },
  {
    route: '/platform/security/',
    selector: '.mkt-security-card--before h3',
    was: 1.17,
    why: 'same translucent-card defect on the security page',
  },
  {
    route: '/platform/security/',
    selector: '.mkt-security-card li',
    was: 1.08,
    why: 'same card, list ink',
  },
  {
    route: '/platform/security/',
    selector: '.mkt-security-card--after h3',
    was: 1.54,
    why: 'same card, accent heading',
  },
  {
    route: '/platform/security/',
    selector: '.mkt-security-handoff-grid a',
    was: 1.44,
    why: 'same self-coloured-anchor defect on the security page',
  },
  {
    route: '/platform/security/',
    selector: '.mkt-trust-evidence-chip--verified',
    was: 4.34,
    why: 'the accent used as its own label on a 12% tint of itself',
  },
];

test.describe('marketing colour-contrast tokens', () => {
  for (const c of CASES) {
    test(`${c.route} ${c.selector} meets WCAG AA`, async ({ page }) => {
      await page.goto(c.route, { waitUntil: 'load' });
      const locator = page.locator(c.selector).first();
      await expect(locator, `${c.selector} not present on ${c.route}`).toHaveCount(1);
      // Scroll-reveal (.rmc-reveal / [data-mkt-reveal]) animates opacity from 0,
      // and a mid-transition reading reports a colour nobody ever sees. Poll for
      // a STABLE reading rather than for opacity === 1: a de-emphasised list item
      // sits at a steady opacity below 1 on purpose, and demanding 1 would make
      // the test hang on exactly the defect it exists to catch.
      await locator.scrollIntoViewIfNeeded().catch(() => {});
      let previous = null;
      let stable = null;
      const deadline = Date.now() + 12000;
      while (Date.now() < deadline) {
        const now = await page.evaluate(measureContrastAll, c.selector);
        if (now && previous && now.worst.ratio === previous.worst.ratio) {
          stable = now;
          break;
        }
        previous = now;
        await page.waitForTimeout(350);
      }
      const result = stable || previous;
      expect(result, `${c.selector} not present on ${c.route}`).not.toBeNull();
      const m = result.worst;
      expect(
        m.ratio,
        `${c.why}
  worst of ${result.count} match(es): ${m.ratio}:1 ` +
          `(${m.fg} on ${m.bg}, ${m.fontSize}px/${m.fontWeight}, opacity ${m.opacity}) ` +
          `— needs ${m.required}:1; was ${c.was}:1 before the token fix`,
      ).toBeGreaterThanOrEqual(m.required);
    });
  }
});
