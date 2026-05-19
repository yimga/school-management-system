// @ts-check
/**
 * Marketplace / App Catalog chromatic regression — dark mode must not leave
 * proof-app-card surfaces on a solid white backdrop with light text.
 *
 * Requires Django on BASE_URL. Set MARKETPLACE_CHROMATIC_AUTH=1 with storage
 * state for super + tenant when running full routes.
 */
const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const AUTH = process.env.MARKETPLACE_CHROMATIC_AUTH === '1';

const ROUTES = [
  {
    path: '/super/marketplace/apps/',
    label: 'manager-app-catalog',
    cardSelector: '#cp-main-content .proof-app-card',
    auth: true,
  },
  {
    path: '/t/demo-school/settings/app-catalog/',
    label: 'tenant-app-catalog',
    cardSelector: '.tenant-app-catalog-wrap .proof-app-card',
    auth: true,
  },
  {
    path: '/ops/incidents/',
    label: 'platform-incidents-table',
    cardSelector: '#cp-main-content .table tbody td',
    auth: true,
  },
  {
    path: '/siteconfig/ai-center/',
    label: 'ai-center-assistants',
    cardSelector: '#cp-main-content .list-group-item',
    auth: true,
  },
];

function parseRgb(cssColor) {
  const m = String(cssColor || '').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!m) return null;
  return { r: Number(m[1]), g: Number(m[2]), b: Number(m[3]) };
}

function isNearWhite(rgb) {
  if (!rgb) return false;
  return rgb.r >= 250 && rgb.g >= 250 && rgb.b >= 250;
}

function luminance({ r, g, b }) {
  const ch = (c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

function contrastRatio(fg, bg) {
  const l1 = luminance(fg);
  const l2 = luminance(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

async function forceDark(page) {
  await page.evaluate(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', 'dark');
    root.setAttribute('data-resolved-theme', 'dark');
    root.setAttribute('data-bs-theme', 'dark');
    root.classList.add('dark');
    root.style.colorScheme = 'dark';
  });
}

test.use({ baseURL: BASE_URL });

test.describe('marketplace proof surfaces — dark chromatic', () => {
  for (const route of ROUTES) {
    test(`${route.label} cards are not white slabs in dark mode`, async ({ page }) => {
      if (route.auth && !AUTH) {
        test.skip(true, 'Set MARKETPLACE_CHROMATIC_AUTH=1 for authenticated catalog routes');
      }
      const resp = await page.goto(route.path, { waitUntil: 'domcontentloaded' });
      expect(resp?.status()).toBeLessThan(500);
      await forceDark(page);
      await page.waitForTimeout(300);
      const cards = page.locator(route.cardSelector);
      const count = await cards.count();
      if (count === 0) {
        test.skip(true, `No ${route.cardSelector} on page (empty catalog or auth required)`);
      }
      const sample = Math.min(count, 3);
      for (let i = 0; i < sample; i += 1) {
        const card = cards.nth(i);
        const bg = await card.evaluate((el) => getComputedStyle(el).backgroundColor);
        const rgb = parseRgb(bg);
        expect.soft(isNearWhite(rgb), `card ${i} background ${bg}`).toBe(false);
        const muted = card.locator('.text-muted').first();
        if ((await muted.count()) > 0) {
          const fgCss = await muted.evaluate((el) => getComputedStyle(el).color);
          const fg = parseRgb(fgCss);
          const ratio = contrastRatio(fg, rgb);
          expect.soft(ratio, `card ${i} muted contrast`).toBeGreaterThan(4.5);
        }
      }
    });
  }

  test('proof-pages.css is linked on manager catalog', async ({ page }) => {
    if (!AUTH) test.skip(true, 'Set MARKETPLACE_CHROMATIC_AUTH=1');
    await page.goto('/super/marketplace/apps/', { waitUntil: 'domcontentloaded' });
    const link = page.locator('link[href*="proof-pages"]');
    await expect.soft(link).toHaveCount(1);
  });
});
