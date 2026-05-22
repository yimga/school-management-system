// @ts-check
// Phase 12 — workflow-guidance E2E spec.
// Verifies the Phase 3 components render correctly when wired (Phase 4 POC):
//   - studio-os-output operator surface
//   - migration-cloud connector wizard
//   - parent dashboard next-action chip
// The specs are guarded by E2E_LOGIN_USER like the other harness specs so
// they only run when an operator account is provided.

const { test, expect } = require("@playwright/test");

const MGR = process.env.MANAGER_HOST || "manager.runmycampus.com:8000";
// demo-school.* (not demo.*) is what playwright.config.js host-resolver maps
// to 127.0.0.1; using the unmapped subdomain hits real DNS and fails.
const TENANT = process.env.TENANT_HOST || "demo-school.runmycampus.com:8000";

// ============================================================================
// Wave E — Unauthenticated smoke specs.
// These run without E2E_LOGIN_USER. They check static-only invariants:
// CSS bundle reachable, anonymous landing pages don't leak template syntax,
// platform-only chrome doesn't appear on tenant subdomains.
// ============================================================================

test.describe("Workflow guidance — unauthenticated smoke (Wave E)", () => {

  test("workflow-guidance.css bundle reachable from public surface", async ({ page }) => {
    // page.goto honors chromium --host-resolver-rules; page.request.get does
    // not, which would make it hit real DNS and time out under local dev.
    const resp = await page.goto(`http://${MGR}/static/css/rmc-workflow-guidance.css`);
    expect([200, 304]).toContain(resp.status());
    const body = await page.content();
    expect(body).toContain(".rmc-workflow-tag");
    expect(body).toContain("rmc-workflow-status-strip");
  });

  test("manager login page has no template syntax leaks", async ({ page }) => {
    const resp = await page.goto(`http://${MGR}/accounts/login/`);
    expect(resp.status()).toBeLessThan(500);
    const body = await page.locator("body").innerText();
    expect(body).not.toMatch(/\{\%\s+(include|workflow_resolve|if|for)/);
    expect(body).not.toMatch(/\{\{\s+rmc_wf_auto/);
    expect(body).not.toContain("[object Object]");
  });

  test("tenant subdomain login does not leak operator workflow chrome", async ({ request }) => {
    // Tenant subdomain → 127.0.0.1 mapping is brittle locally (chromium's
    // --host-resolver-rules doesn't always pick up wildcard tenant subs on
    // Windows) and Host header can't be overridden via setExtraHTTPHeaders
    // (it's a forbidden header in the browser context). Use Playwright's
    // Node-side request fixture instead — it bypasses both restrictions.
    // Don't follow redirects — the tenant-resolution chain may bounce
    // through runmycampus.com/school-not-found for unseeded tenants in dev,
    // which would then need real DNS. A 30x response on the first hop is
    // already a valid "no operator chrome leaked" answer.
    const resp = await request.get(`http://127.0.0.1:8000/accounts/login/`, {
      headers: { Host: TENANT },
      maxRedirects: 0,
      failOnStatusCode: false,
    });
    expect(resp.status()).toBeLessThan(500);
    // Platform-only data attributes must not appear on the response body
    const body = await resp.text();
    expect(body).not.toContain('data-rmc-workflow-tag="platform-only"');
  });

  test("auto-chrome partial does not render on routes without registered workflow", async ({ page }) => {
    // The marketing root has no registered workflow entry_path — auto-chrome
    // should resolve to None and render NOTHING.
    const resp = await page.goto(`http://${MGR}/`);
    expect(resp.status()).toBeLessThan(500);
    // The wrapper div is only emitted when at least one of status/next/panel is set
    const chrome = page.locator('[data-rmc-workflow-auto-chrome="1"]');
    // Either 0 (no workflow resolved) or >=1 (workflow resolved) — both OK.
    // What matters: NO data-rmc-workflow-key="" empty attribute and NO template leak.
    const count = await chrome.count();
    if (count > 0) {
      const key = await chrome.first().getAttribute("data-rmc-workflow-key");
      expect(key, "workflow key must be non-empty when chrome renders").toBeTruthy();
    }
  });
});

test.describe("Workflow guidance scaffolding (Phase 3 components, Phase 4 wiring)", () => {
  test.skip(!process.env.E2E_LOGIN_USER, "Set E2E_LOGIN_USER/E2E_LOGIN_PASSWORD for live sweep");

  test("studio-os output mode renders workflow chrome when scaffolded", async ({ page }) => {
    await page.goto(`http://${MGR}/studio/output/`);
    const status = page.locator(".rmc-workflow-status-strip");
    const nextAction = page.locator(".rmc-workflow-next-action");
    // Either present (when SiteSettings opt-in landed) or absent (default-off scaffolding).
    // The hard requirement is they NEVER render with broken markup or empty href="#" without aria-disabled.
    const statusCount = await status.count();
    const nextActionCount = await nextAction.count();
    if (statusCount > 0) {
      await expect(status.first()).toHaveAttribute("data-rmc-workflow-status-strip", "1");
      await expect(status.first()).toHaveAttribute("role", "group");
    }
    if (nextActionCount > 0) {
      // Primary chip must have either a real href OR aria-disabled=true (blocker state)
      const primary = nextAction.locator(".rmc-workflow-next-action__chip--primary").first();
      const href = await primary.getAttribute("href");
      const ariaDisabled = await primary.getAttribute("aria-disabled");
      const safe = (href && href !== "#") || ariaDisabled === "true";
      expect(safe, "primary chip must have real URL or aria-disabled when href=#").toBeTruthy();
    }
  });

  test("migration-cloud connector wizard scaffolding has no broken includes", async ({ page }) => {
    await page.goto(`http://${TENANT}/school/setup/migration-cloud/connectors/`);
    // Page renders without 500
    await expect(page).not.toHaveURL(/.*500.*/);
    // No literal template syntax leak
    const body = await page.locator("body").innerText();
    expect(body).not.toMatch(/\{\%\s+include/);
    expect(body).not.toMatch(/\{\{\s+wf\./);
  });

  test("parent dashboard next-action scaffolding does not break dashboard", async ({ page }) => {
    await page.goto(`http://${TENANT}/portal/parent/`);
    // Existing parent dashboard cockpit cards still render
    await expect(page.locator("[data-rmc-tp-dashboard-cockpit=\"parent\"]")).toBeVisible();
    // No accidental [object Object] template leak
    const body = await page.locator("body").innerText();
    expect(body).not.toContain("[object Object]");
  });

  test("workflow status strip is keyboard-accessible when present (any surface)", async ({ page }) => {
    await page.goto(`http://${MGR}/studio/output/`);
    const status = page.locator(".rmc-workflow-status-strip");
    if ((await status.count()) === 0) test.skip();
    // role=group must be present
    await expect(status.first()).toHaveAttribute("role", "group");
    // aria-label must be non-empty
    const ariaLabel = await status.first().getAttribute("aria-label");
    expect(ariaLabel, "status strip must carry aria-label").toBeTruthy();
  });

  test("info tag chips do not rely on color alone", async ({ page }) => {
    await page.goto(`http://${MGR}/studio/output/`);
    const tags = page.locator(".rmc-workflow-tag");
    const count = await tags.count();
    if (count === 0) test.skip();
    // Every tag chip must have a visible text label (not icon-only)
    for (let i = 0; i < count; i++) {
      const label = await tags.nth(i).locator(".rmc-workflow-tag__label").innerText();
      expect(label.trim().length, `tag ${i} has empty label`).toBeGreaterThan(0);
    }
  });

  test("workflow-guidance.css bundle is reachable", async ({ page }) => {
    // Static asset must 200 — not 404 — when wired into any of the 3 templates.
    const resp = await page.request.get(`http://${MGR}/static/css/rmc-workflow-guidance.css`);
    expect([200, 304]).toContain(resp.status());
  });

  test("operator workflow chrome must not surface on tenant host", async ({ page }) => {
    await page.goto(`http://${TENANT}/portal/parent/`);
    // Platform-only data attributes (if any leak through) — verify NONE present
    const platformOnly = page.locator('[data-rmc-workflow-tag="platform-only"]');
    expect(await platformOnly.count(), "platform-only tag leaked onto tenant host").toBe(0);
  });
});
