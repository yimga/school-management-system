// @ts-check
/**
 * Tenant login for Playwright — supports host-based tenant URLs (preferred) or
 * path-based /t/<slug>/ for any provisioned school tenant.
 */

const TENANT_SLUG = (process.env.TENANT_SLUG || 'gilead-school').replace(/^\/+|\/+$/g, '');
const TENANT_PORT = process.env.VISUAL_QA_PORT || '8000';
const TENANT_HOST =
  process.env.VISUAL_QA_TENANT_HOST || `${TENANT_SLUG}.runmycampus.com`;
const TENANT_ORIGIN = (
  process.env.TENANT_BASE_URL || `http://127.0.0.1:${TENANT_PORT}`
).replace(/\/$/, '');

function _inferTenantRouting() {
  const explicit = (process.env.TENANT_ROUTING || '').trim().toLowerCase();
  if (explicit === 'path' || explicit === 'host') {
    return explicit;
  }
  try {
    const host = new URL(TENANT_ORIGIN).hostname;
    if (host === '127.0.0.1' || host === 'localhost') {
      return 'path';
    }
  } catch {
    // fall through
  }
  return 'host';
}

const TENANT_ROUTING = _inferTenantRouting();

function tenantPrefix() {
  const raw = (process.env.TENANT_PREFIX || `/t/${TENANT_SLUG}`).trim();
  const normalized = raw.replace(/\\/g, '/');
  if (normalized.startsWith('/')) {
    return normalized.replace(/\/$/, '');
  }
  return `/t/${TENANT_SLUG}`;
}

function tenantUrl(path) {
  const suffix = path.startsWith('/') ? path : `/${path}`;
  if (TENANT_ROUTING === 'path') {
    return `${TENANT_ORIGIN}${tenantPrefix()}${suffix}`;
  }
  return `${TENANT_ORIGIN}${suffix}`;
}

/**
 * @param {import('@playwright/test').Page} page
 */
function _isRunmycampusMarketingHost(hostname) {
  return (
    hostname === 'runmycampus.com' ||
    hostname.endsWith('.runmycampus.com')
  );
}

function _pathWithTenantPrefix(pathname) {
  const prefix = tenantPrefix();
  let path = pathname || '/';
  if (path.startsWith(prefix)) {
    return path;
  }
  const stripped = path.replace(/^\/t\/[^/]+/, '') || '/';
  const suffix = stripped.startsWith('/') ? stripped : `/${stripped}`;
  return `${prefix}${suffix}`;
}

async function ensureTenantOrigin(page) {
  let current;
  try {
    current = new URL(page.url());
  } catch {
    return;
  }
  const targetOrigin = new URL(TENANT_ORIGIN);
  const sameOrigin =
    current.hostname === targetOrigin.hostname &&
    (current.port || '80') === (targetOrigin.port || '80');
  if (sameOrigin && TENANT_ROUTING !== 'path') {
    return;
  }
  if (
    sameOrigin &&
    TENANT_ROUTING === 'path' &&
    current.pathname.startsWith(tenantPrefix())
  ) {
    return;
  }
  const tenantSubdomain = `${TENANT_SLUG}.runmycampus.com`;
  if (
    current.hostname === tenantSubdomain &&
    (current.port || '80') === (targetOrigin.port || '80')
  ) {
    return;
  }
  const escapedHost =
    TENANT_ROUTING === 'path' ||
    current.hostname === 'runmycampus.com' ||
    (current.hostname.endsWith('.runmycampus.com') &&
      (current.port || '80') !== (targetOrigin.port || '80'));
  if (!escapedHost) {
    return;
  }
  const path = TENANT_ROUTING === 'path' ? _pathWithTenantPrefix(current.pathname) : current.pathname;
  const target = new URL(
    path + current.search + current.hash,
    `${TENANT_ORIGIN}/`,
  );
  if (target.toString() === page.url()) {
    return;
  }
  await page.goto(target.toString(), {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ role?: string, username?: string, password?: string }} [opts]
 */
async function tenantLogin(page, opts = {}) {
  const username =
    opts.username ||
    process.env.VISUAL_QA_TEACHER_USERNAME ||
    process.env.E2E_USERNAME ||
    'teacher1';
  const password =
    opts.password ||
    process.env.VISUAL_QA_TEACHER_PASSWORD ||
    process.env.E2E_PASSWORD ||
    'Sch00l_1234';
  const role = opts.role || 'teacher';

  await page.goto(tenantUrl('/authentication/login/'), {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await ensureTenantOrigin(page);
  if ((await page.locator('input[name="username"]').count()) === 0) {
    return false;
  }
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    const roleValue = String(role || '').trim();
    const candidates = [
      roleValue,
      roleValue.toUpperCase(),
      roleValue.toLowerCase(),
      roleValue.charAt(0).toUpperCase() + roleValue.slice(1).toLowerCase(),
    ].filter(Boolean);
    let selected = false;
    for (const candidate of candidates) {
      try {
        await roleSelect.selectOption(candidate, { timeout: 1000 });
        selected = true;
        break;
      } catch {
        // Try the next value/label variant.
      }
    }
    if (!selected) {
      const available = await roleSelect.locator('option').evaluateAll((options) =>
        options.map((option) => ({
          value: option.value,
          label: option.textContent || '',
        }))
      );
      const match = available.find((option) =>
        candidates.some((candidate) =>
          option.label.trim().toLowerCase() === candidate.toLowerCase()
        )
      );
      if (match) {
        await roleSelect.selectOption(match.value);
      }
    }
  }
  await page.getByRole('button', { name: /log in/i }).click();
  await page.waitForURL(
    (url) => !/\/authentication\/login\/?$/i.test(url.pathname),
    { timeout: 90000, waitUntil: 'domcontentloaded' }
  );
  await ensureTenantOrigin(page);
  return true;
}

module.exports = {
  TENANT_SLUG,
  TENANT_ROUTING,
  TENANT_HOST,
  tenantPrefix,
  TENANT_ORIGIN,
  tenantUrl,
  ensureTenantOrigin,
  tenantLogin,
};
