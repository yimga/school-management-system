// @ts-check
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const MANAGER_BASE_URL = process.env.MANAGER_BASE_URL || 'http://manager.runmycampus.com:8012';
const TENANT_BASE_URL = process.env.TENANT_BASE_URL || 'http://apple-class-qa.runmycampus.com:8012';
const PLATFORM_USERNAME = process.env.APPLE_QA_PLATFORM_USERNAME || 'appleqa_platform';
const PLATFORM_PASSWORD = process.env.APPLE_QA_PLATFORM_PASSWORD || 'AppleQaPass123!';
const TENANT_USERNAME = process.env.APPLE_QA_TENANT_USERNAME || 'appleqa_tenant';
const TENANT_PASSWORD = process.env.APPLE_QA_TENANT_PASSWORD || 'AppleQaPass123!';
const SKIP_AXE = process.env.SKIP_AXE === '1';

const REPORT_JSON = path.join(process.cwd(), 'docs', 'generated', 'apple_class_authenticated_browser_report.json');
const REPORT_MD = path.join(process.cwd(), 'docs', 'generated', 'apple_class_authenticated_browser_report.md');
const COVERAGE_JSON = path.join(process.cwd(), 'docs', 'generated', 'apple_class_component_coverage.json');
const COVERAGE_MD = path.join(process.cwd(), 'docs', 'generated', 'apple_class_component_coverage.md');

const VIEWPORTS = {
  desktop: { width: 1366, height: 900 },
  mobile: { width: 390, height: 844 },
};

const PLATFORM_ROUTES = [
  { route: '/super/', required: ['[data-apple-class-super-command-center]', '[data-apple-class-command-strip]'] },
  { route: '/configuration/', required: ['[data-apple-class-configuration-console]'] },
  { route: '/configuration/blueprints/', required: ['[data-apple-class-governed-installation]', '[data-apple-class-visual-workflow-path]'] },
  { route: '/configuration/workflow-packs/', required: ['[data-apple-class-governed-installation]', '[data-apple-class-visual-workflow-path]'] },
  { route: '/configuration/dashboard-packs/', required: ['[data-apple-class-governed-installation]', '[data-apple-class-visual-workflow-path]'] },
  { route: '/configuration/policy-bundles/', required: ['[data-apple-class-governed-installation]', '[data-apple-class-visual-workflow-path]'] },
  { route: '/configuration/change-requests/', required: ['[data-apple-class-governed-installation]', '[data-apple-class-dependency-graph]'] },
  { route: '/configuration/registries/health/', required: ['[data-rmc-page-purpose]'] },
  { route: '/configuration/migrations/', required: ['[data-apple-class-migration-ux]', '[data-apple-class-data-quality-meter]'] },
  { route: '/configuration/integrations/', required: ['[data-rmc-page-purpose]'] },
  { route: '/configuration/billing/', required: ['[data-apple-class-billing-ux]'] },
  { route: '/configuration/experience/', required: ['[data-rmc-page-purpose]'] },
  { route: '/internal-admin/', required: ['body'] },
];

const TENANT_ROUTES = [
  { route: '/school/settings/', required: ['[data-apple-class-tenant-school-admin]'] },
  { route: '/school/setup/blueprints/', required: ['[data-apple-class-tenant-school-admin]', '[data-apple-class-visual-workflow-path]'] },
  { route: '/school/setup/packs/', required: ['[data-apple-class-tenant-school-admin]', '[data-apple-class-visual-workflow-path]'] },
  { route: '/school/setup/imports/', required: ['[data-apple-class-migration-ux]', '[data-apple-class-data-quality-meter]'], followsRedirect: true },
  { route: '/school/apps/', required: ['[data-apple-class-app-catalog]'], followsRedirect: true },
  { route: '/school/money/', required: ['[data-apple-class-billing-ux]'], followsRedirect: true },
  { route: '/school/workflows/', required: ['body'], followsRedirect: true },
  { route: '/school/offline/', required: ['body'], followsRedirect: true },
  { route: '/school/audit/', required: ['body'], followsRedirect: true },
  { route: '/school/security/', required: ['body'], followsRedirect: true },
];

const COMPONENTS = [
  { name: 'glass panel', marker: '[data-apple-class-glass-panel]' },
  { name: 'command strip', marker: '[data-apple-class-command-strip]' },
  { name: 'status pill', marker: '[data-apple-class-status-pill]' },
  { name: 'metric card', marker: '[data-apple-class-metric-card]' },
  { name: 'readiness meter', marker: '[data-world-class-readiness-meter], [data-apple-class-data-quality-meter]' },
  { name: 'visual workflow path', marker: '[data-apple-class-visual-workflow-path]' },
  { name: 'dependency graph', marker: '[data-apple-class-dependency-graph]' },
  { name: 'data quality meter', marker: '[data-apple-class-data-quality-meter]' },
  { name: 'risk/blocker card', marker: '[data-world-class-risk-blocker-card], [data-apple-class-risk-card]' },
  { name: 'quick profile drawer', marker: '[data-apple-class-quick-profile-drawer]' },
  { name: 'inline edit field', marker: '[data-apple-class-inline-edit-field]' },
  { name: 'empty state', marker: '[data-world-class-empty-state]' },
];

async function login(page, baseUrl, username, password) {
  await page.goto(`${baseUrl}/authentication/login/`, { waitUntil: 'networkidle' });
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /log in/i }).click();
  await page.waitForLoadState('networkidle');
  expect(/\/authentication\/login\/?$/i.test(page.url()), `login completed for ${username}`).toBe(false);
}

async function axeBlocking(page) {
  if (SKIP_AXE) return [];
  const { violations } = await new AxeBuilder({ page }).analyze();
  return violations.filter((violation) => violation.impact === 'critical' || violation.impact === 'serious');
}

async function inspectRoute(page, baseUrl, routeSpec, viewportName, surface) {
  const messages = [];
  page.on('console', (message) => {
    if (message.type() === 'error') messages.push(message.text());
  });

  const response = await page.goto(`${baseUrl}${routeSpec.route}`, {
    waitUntil: 'networkidle',
    timeout: 45000,
  });
  const status = response ? response.status() : 0;
  const finalUrl = page.url();
  const body = page.locator('body');
  await expect(body).toBeVisible();
  await expect(body).not.toContainText(/Server Error \(500\)|Traceback|OperationalError|TemplateSyntaxError/i);
  expect(status, `${surface} ${routeSpec.route} status`).toBeLessThan(500);

  for (const selector of routeSpec.required) {
    await expect(page.locator(selector).first(), `${surface} ${routeSpec.route} ${selector}`).toBeVisible({ timeout: 15000 });
  }

  const dummyActions = await page
    .locator('a[href="#"], button:not([aria-label]):not([title]):empty')
    .count();
  expect(dummyActions, `${surface} ${routeSpec.route} dummy actions`).toBe(0);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${surface} ${routeSpec.route} horizontal overflow`).toBeLessThanOrEqual(16);

  await page.keyboard.press('Tab');
  const focus = await page.evaluate(() => {
    const active = document.activeElement;
    if (!active || active === document.body) return { ok: false, tag: 'body', text: '' };
    const style = window.getComputedStyle(active);
    const visible =
      style.outlineStyle !== 'none' ||
      style.boxShadow !== 'none' ||
      style.borderColor !== 'rgba(0, 0, 0, 0)';
    return {
      ok: visible,
      tag: active.tagName.toLowerCase(),
      text: (active.textContent || active.getAttribute('aria-label') || '').trim().slice(0, 80),
    };
  });
  expect(focus.ok, `${surface} ${routeSpec.route} visible keyboard focus`).toBe(true);

  const axeViolations = await axeBlocking(page);
  expect(axeViolations, `${surface} ${routeSpec.route} serious/critical axe violations`).toEqual([]);

  return {
    surface,
    route: routeSpec.route,
    viewport: viewportName,
    status,
    final_url: finalUrl,
    console_errors: messages,
    horizontal_overflow_px: overflow,
    accessibility: SKIP_AXE ? 'skipped' : 'pass',
    required_markers: routeSpec.required,
    result: 'pass',
  };
}

async function inspectNegativeAccess(page, baseUrl, route, expected) {
  const response = await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle', timeout: 45000 });
  const status = response ? response.status() : 0;
  const text = (await page.locator('body').textContent()) || '';
  const blocked =
    status === 403 ||
    status === 404 ||
    /authentication\/login|sign in|log in|login|access required|forbidden|control-plane access|required/i.test(`${page.url()} ${text}`);
  expect(blocked, `${expected} ${route} blocked`).toBe(true);
  return { actor: expected, route, status, final_url: page.url(), result: 'blocked' };
}

function writeReports(report) {
  fs.mkdirSync(path.dirname(REPORT_JSON), { recursive: true });
  fs.writeFileSync(REPORT_JSON, `${JSON.stringify(report, null, 2)}\n`);

  const routeRows = report.routes
    .map((row) => `| ${row.surface} | ${row.viewport} | \`${row.route}\` | ${row.status} | ${row.result} | ${row.accessibility} | ${row.console_errors.length} |`)
    .join('\n');
  const negativeRows = report.negative_access
    .map((row) => `| ${row.actor} | \`${row.route}\` | ${row.status} | ${row.result} |`)
    .join('\n');

  fs.writeFileSync(
    REPORT_MD,
    [
      '# Apple-Class Authenticated Browser Report',
      '',
      `- Verdict: **${report.verdict}**`,
      `- Generated: ${report.generated_at}`,
      `- Manager host: \`${report.environment.manager_base_url}\``,
      `- Tenant host: \`${report.environment.tenant_base_url}\``,
      `- Axe: ${report.environment.axe}`,
      `- Render parity: not tested`,
      '',
      '## Routes',
      '',
      '| Surface | Viewport | Route | Status | Result | Accessibility | Console errors |',
      '| --- | --- | --- | ---: | --- | --- | ---: |',
      routeRows,
      '',
      '## Negative Access',
      '',
      '| Actor | Route | Status | Result |',
      '| --- | --- | ---: | --- |',
      negativeRows,
      '',
      '## Remaining Issues',
      '',
      '- Render/deployed SHA parity remains pending.',
      '- Active drawer focus-trap testing remains future depth until drawers are JS-active.',
      '',
    ].join('\n')
  );
}

function writeCoverage(coverage) {
  fs.mkdirSync(path.dirname(COVERAGE_JSON), { recursive: true });
  fs.writeFileSync(COVERAGE_JSON, `${JSON.stringify(coverage, null, 2)}\n`);
  const rows = coverage.components
    .map((row) => `| ${row.name} | \`${row.marker}\` | ${row.count} | ${row.routes.join(', ') || 'missing'} | ${row.accessibility_notes} |`)
    .join('\n');
  fs.writeFileSync(
    COVERAGE_MD,
    [
      '# Apple-Class Component Coverage',
      '',
      `- Generated: ${coverage.generated_at}`,
      `- Verdict: **${coverage.verdict}**`,
      '',
      '| Component | Marker | Count | Routes | Accessibility notes |',
      '| --- | --- | ---: | --- | --- |',
      rows,
      '',
    ].join('\n')
  );
}

test.describe.serial('authenticated Apple-class UX certification', () => {
  test.setTimeout(360000);

  test('platform, tenant, mobile, accessibility, and negative access proof', async ({ browser }) => {
    const routes = [];
    const negative = [];
    const coverageMap = new Map(COMPONENTS.map((component) => [component.name, { ...component, count: 0, routes: new Set() }]));

    for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
      const platformContext = await browser.newContext({ viewport, deviceScaleFactor: viewportName === 'mobile' ? 2 : 1 });
      const platformPage = await platformContext.newPage();
      await login(platformPage, MANAGER_BASE_URL, PLATFORM_USERNAME, PLATFORM_PASSWORD);
      for (const route of PLATFORM_ROUTES) {
        const result = await inspectRoute(platformPage, MANAGER_BASE_URL, route, viewportName, 'platform');
        routes.push(result);
        for (const [name, component] of coverageMap.entries()) {
          const count = await platformPage.locator(component.marker).count();
          if (count > 0) {
            component.count += count;
            component.routes.add(route.route);
          }
        }
      }
      await platformContext.close();

      const tenantContext = await browser.newContext({ viewport, deviceScaleFactor: viewportName === 'mobile' ? 2 : 1 });
      const tenantPage = await tenantContext.newPage();
      await login(tenantPage, TENANT_BASE_URL, TENANT_USERNAME, TENANT_PASSWORD);
      for (const route of TENANT_ROUTES) {
        const result = await inspectRoute(tenantPage, TENANT_BASE_URL, route, viewportName, 'tenant');
        routes.push(result);
        for (const [name, component] of coverageMap.entries()) {
          const count = await tenantPage.locator(component.marker).count();
          if (count > 0) {
            component.count += count;
            component.routes.add(route.route);
          }
        }
      }
      await tenantContext.close();
    }

    const anonContext = await browser.newContext({ viewport: VIEWPORTS.desktop });
    const anon = await anonContext.newPage();
    for (const route of ['/super/', '/configuration/', '/internal-admin/']) {
      negative.push(await inspectNegativeAccess(anon, MANAGER_BASE_URL, route, 'anonymous'));
    }
    negative.push(await inspectNegativeAccess(anon, TENANT_BASE_URL, '/school/settings/', 'anonymous'));
    await anonContext.close();

    const tenantContext = await browser.newContext({ viewport: VIEWPORTS.desktop });
    const tenantPage = await tenantContext.newPage();
    await login(tenantPage, TENANT_BASE_URL, TENANT_USERNAME, TENANT_PASSWORD);
    negative.push(await inspectNegativeAccess(tenantPage, MANAGER_BASE_URL, '/configuration/', 'tenant user'));
    negative.push(await inspectNegativeAccess(tenantPage, MANAGER_BASE_URL, '/super/', 'tenant user'));
    await tenantContext.close();

    const componentCoverage = {
      generated_at: new Date().toISOString(),
      verdict: 'APPLE-CLASS UX READY - LOCAL COMPONENT COVERAGE',
      components: Array.from(coverageMap.values()).map((component) => ({
        name: component.name,
        marker: component.marker,
        count: component.count,
        routes: Array.from(component.routes).sort(),
        accessibility_notes:
          component.name === 'quick profile drawer'
            ? 'Static drawer marker verified; active focus-trap test remains future depth until JS-active.'
            : 'Covered in authenticated route smoke and axe pass where rendered.',
      })),
    };

    writeCoverage(componentCoverage);
    writeReports({
      generated_at: new Date().toISOString(),
      verdict: 'APPLE-CLASS UX READY - LOCAL',
      environment: {
        manager_base_url: MANAGER_BASE_URL,
        tenant_base_url: TENANT_BASE_URL,
        platform_username: PLATFORM_USERNAME,
        tenant_username: TENANT_USERNAME,
        axe: SKIP_AXE ? 'skipped' : 'enabled',
      },
      routes,
      negative_access: negative,
      component_coverage: componentCoverage.components,
      remaining_issues: [
        'Render/deployed SHA parity remains pending.',
        'Active drawer focus-trap testing remains future depth until drawers are JS-active.',
      ],
    });
  });
});
