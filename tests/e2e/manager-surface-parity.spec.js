// @ts-check
/**
 * Manager host: /super/ ↔ /admin/ surface strip + paired chips (batch 1252+1253).
 * Requires Django on 127.0.0.1:${VISUAL_QA_PORT:-8010} with Host manager.runmycampus.com.
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const { ensureManagerHost, AUTH_STATE_PATH } = require('./helpers/manager-login');

const MANAGER_HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const MANAGER_PORT = process.env.VISUAL_QA_PORT || '8012';
const MANAGER_BASE_URL =
  process.env.MANAGER_BASE_URL ||
  process.env.BASE_URL ||
  `http://${MANAGER_HOST}:${MANAGER_PORT}`;

const MANAGER_USERNAME = process.env.VISUAL_QA_USERNAME || 'visualqa_admin';
const MANAGER_PASSWORD = process.env.VISUAL_QA_PASSWORD || 'VisualQaPass123!';

const PROBES_JSON = path.join(
  __dirname,
  '../../docs/generated/manager_surface_browser_probes.json'
);

/** @type {Array<{slug:string,path:string,expect_strip:boolean,expect_paired:boolean,paired_operator?:boolean}>} */
function loadProbes() {
  if (fs.existsSync(PROBES_JSON)) {
    const data = JSON.parse(fs.readFileSync(PROBES_JSON, 'utf8'));
    if (Array.isArray(data.probes)) {
      return data.probes.filter((row) => row.path);
    }
  }
  return [
    { slug: 'super_dashboard', path: '/super/', expect_strip: true, expect_paired: false },
    {
      slug: 'super_schools',
      path: '/super/schools/',
      expect_strip: true,
      expect_paired: true,
    },
    {
      slug: 'super_marketplace',
      path: '/super/marketplace/',
      expect_strip: true,
      expect_paired: true,
    },
    {
      slug: 'super_security',
      path: '/super/security/',
      expect_strip: true,
      expect_paired: true,
    },
    {
      slug: 'configuration_center',
      path: '/configuration/',
      expect_strip: true,
      expect_paired: false,
    },
    { slug: 'admin_index', path: '/admin/', expect_strip: true, expect_paired: false },
    {
      slug: 'admin_schools',
      path: '/admin/schools/school/',
      expect_strip: true,
      expect_paired: true,
      paired_operator: true,
    },
    {
      slug: 'admin_marketplace_apps',
      path: '/admin/integrations_marketplace/marketplaceapp/',
      expect_strip: true,
      expect_paired: true,
      paired_operator: true,
    },
  ];
}

/** Super routes first — /admin/ popup flags can poison the shared session for /super/*. */
const PROBES = loadProbes().sort((a, b) => {
  const rank = (probe) => {
    if (probe.path.startsWith('/super/')) return 0;
    if (probe.slug === 'configuration_center') return 1;
    if (probe.path.startsWith('/admin/')) return 2;
    return 1;
  };
  return rank(a) - rank(b) || a.slug.localeCompare(b.slug);
});

test.use({
  baseURL: MANAGER_BASE_URL,
  viewport: { width: 1400, height: 900 },
});

test('version endpoint returns JSON commit_sha', async ({ playwright }) => {
  const ctx = await playwright.request.newContext({
    baseURL: `http://127.0.0.1:${MANAGER_PORT}`,
    extraHTTPHeaders: { Host: MANAGER_HOST },
  });
  try {
    const response = await ctx.get('/-/version/', {
      headers: { Accept: 'application/json' },
    });
    expect(response.ok()).toBeTruthy();
    const contentType = response.headers()['content-type'] || '';
    expect(contentType).toMatch(/application\/json/i);
    const payload = await response.json();
    expect(payload).toHaveProperty('commit_sha');
  } finally {
    await ctx.dispose();
  }
});

test.describe('manager surface parity (authenticated)', () => {
  test.describe.configure({ mode: 'serial', timeout: 120000 });

  test.use({
    storageState: AUTH_STATE_PATH,
  });

  test.beforeEach(async ({ page }) => {
    await ensureManagerHost(page);
  });

  for (const probe of PROBES) {
    test(`strip + paired chips: ${probe.slug}`, async ({ page }) => {
      const response = await page.goto(probe.path, {
        waitUntil: 'domcontentloaded',
        timeout: 60000,
      });
      await ensureManagerHost(page);
      expect(response?.status(), probe.path).toBeLessThan(400);

      if (probe.expect_strip) {
        await expect(page.locator('[data-rmc-operator-surface-strip]')).toBeVisible({
          timeout: 20000,
        });
      }

      if (probe.path.startsWith('/admin/')) {
        await expect(page.locator('.admin-cp-unified-page')).toBeAttached({ timeout: 30000 });
        await expect(page.locator('#cpSidebarNav').first()).toBeAttached({ timeout: 30000 });
      }

      if (probe.expect_paired) {
        const paired = page.locator('.rmc-operator-surface-strip__pill--paired');
        await expect(paired.first()).toBeVisible();
        const label = probe.paired_operator
          ? /open operator view/i
          : /open platform admin/i;
        await expect(paired.first()).toContainText(label);
      }
    });
  }
});
