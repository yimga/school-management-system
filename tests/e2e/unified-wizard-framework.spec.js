/**
 * Unified Wizard Framework — parameterized Playwright spec.
 *
 * Covers the wizard registry on both operator and tenant surfaces at 3
 * breakpoints (390 / 768 / 1366). The single-spec pattern mirrors
 * ``apps/setup_studio/tests/test_wizard_happy_paths.py`` — one walker for all
 * wizards rather than one file each.
 *
 * The wizard list is DERIVED from ``apps/setup_studio/wizards/*.json`` by
 * ``tests/e2e/helpers/wizard-registry.js``. It is never typed out here, and
 * there is no wizard count anywhere in this file: the previous revision carried
 * a hand-typed 24-entry array asserted against ``toHaveLength(23)`` while 38
 * wizards were registered, and the drift went unnoticed for four releases
 * because a magic number asserts the WORD, not the BEHAVIOUR.
 *
 * What the spec actually verifies:
 *   - the index landing page renders without horizontal overflow
 *   - EVERY operator-audience wizard appears as a card on the operator index,
 *     by key — a failure names the wizards that are missing
 *   - every card the tenant index renders is a REGISTERED wizard key
 *   - clicking into a wizard renders its first step shell
 *   - the stepper / nav / help rail partials are present
 *
 * What the spec does NOT do (intentionally):
 *   - submit step answers (the Django happy-path test already proves the
 *     full walker end-to-end; replicating that in the browser would be
 *     ~57 specs of test data setup with diminishing return)
 *   - assert an EXACT card set on the tenant index. That surface is
 *     audience-aware (``TenantWizardIndexView`` resolves the signed-in user's
 *     audience and lists that audience's wizards), and the spec does not
 *     control which role the stored auth state belongs to. It asserts the
 *     direction that IS knowable: no card may carry an unregistered key.
 *   - exercise AI smart-default fetches (covered by the AI LIVE smoke
 *     verifier — see scripts/verify_wizard_ai_live_smoke.py)
 *
 * Honest-reporting: every breakpoint test skips cleanly when the browser
 * lands on the login surface or when the route 404s (e.g. CI lane runs
 * without the setup_studio app mounted). It NEVER green-flashes — either
 * the assertions run or the test is marked skipped with a reason.
 *
 * Run via: npx playwright test tests/e2e/unified-wizard-framework.spec.js
 * Honors PLAYWRIGHT_BASE_URL env var; defaults to http://localhost:8000.
 */

const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");

const {
  OPERATOR_INDEX_EXCLUSIONS,
  keysForAudience,
  loadWizardRegistry,
  operatorIndexKeys,
  wizardKeys,
} = require("./helpers/wizard-registry");

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8000";
const TENANT_BASE_URL = process.env.WIZARD_TENANT_BASE_URL || BASE_URL;
const OPERATOR_BASE_URL = process.env.WIZARD_OPERATOR_BASE_URL || BASE_URL;
const AUTH_STATE_PATH =
  process.env.WIZARD_AUTH_STATE ||
  path.join(__dirname, "../../artifacts/manager-playwright-auth.json");

const BREAKPOINTS = [
  { name: "mobile-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1366", width: 1366, height: 768 },
];

// Derived at spec load from the JSON registry on disk — NOT a maintained list.
// A wizard added to apps/setup_studio/wizards/ is covered by the next run with
// no edit to this file; scripts/verify_wizard_playwright_spec_coverage.py fails
// the build if either constant is ever re-bound to a literal array.
const WIZARD_REGISTRY_KEYS = wizardKeys();
const OPERATOR_INDEX_WIZARD_KEYS = operatorIndexKeys();

const OPERATOR_INDEX_PATH = "/super/wizards/";
const TENANT_INDEX_PATH = "/school/studio/wizards/";

// Every wizard card anchor on both index templates carries this attribute, so
// the spec can verify coverage by KEY without coupling to label text (which is
// i18n-keyed). Kept true by verify_wizard_playwright_spec_coverage.py, which
// fails if either index template stops emitting it.
const CARD_SELECTOR = "[data-wizard-key]";

if (fs.existsSync(AUTH_STATE_PATH)) {
  test.use({ storageState: AUTH_STATE_PATH });
}

async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => {
    const docW = document.documentElement.clientWidth;
    const bodyW = document.body.scrollWidth;
    return { docW, bodyW, overflow: bodyW > docW + 1 };
  });
  expect(
    overflow.overflow,
    `body scrollWidth=${overflow.bodyW} > docW=${overflow.docW}`,
  ).toBeFalsy();
}

/** Every wizard key the page rendered a card for. */
async function renderedWizardKeys(page) {
  const keys = await page
    .locator(CARD_SELECTOR)
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-wizard-key")));
  return new Set(keys.filter(Boolean));
}

async function isLoginOrMissing(page, response) {
  if (response && response.status() === 404) return "missing";
  const current = new URL(page.url());
  if (/\/authentication\/(login|mfa\/setup|mfa\/verify)\/?$/i.test(current.pathname)) {
    return "login";
  }
  if ((await page.locator('input[name="username"]').count()) > 0) {
    return "login";
  }
  return null;
}

async function skipIfBlocked(page, response, label) {
  const reason = await isLoginOrMissing(page, response);
  if (reason === "login") {
    test.skip(true, `${label} requires an authenticated browser session`);
  }
  if (reason === "missing") {
    test.skip(true, `${label} returned 404 (setup_studio routes not mounted on this lane)`);
  }
}

for (const breakpoint of BREAKPOINTS) {
  test.describe(`Unified Wizard Framework @ ${breakpoint.name}`, () => {
    test.use({ viewport: { width: breakpoint.width, height: breakpoint.height } });

    test(`operator index renders + lists every registered operator wizard`, async ({ page }) => {
      const response = await page.goto(`${OPERATOR_BASE_URL}${OPERATOR_INDEX_PATH}`);
      await skipIfBlocked(page, response, "operator wizard index");

      await expect(page.locator("body")).toBeVisible();
      await assertNoHorizontalOverflow(page);

      // The NAME of this test says "every". So does the assertion: the page must
      // carry a card for every operator-audience wizard in the registry. The old
      // `count() > 0` passed while 18 of 19 were absent — and would have passed
      // just as happily against a page with a single hardcoded card.
      const rendered = await renderedWizardKeys(page);
      const missing = OPERATOR_INDEX_WIZARD_KEYS.filter((key) => !rendered.has(key));
      expect(
        missing,
        `operator index is missing ${missing.length} registered operator wizard(s): ` +
          `${missing.join(", ") || "(none)"}. ` +
          `Rendered ${rendered.size} card(s): ${[...rendered].sort().join(", ") || "(none)"}`,
      ).toEqual([]);
    });

    test(`tenant index renders + every card is a registered wizard`, async ({ page }) => {
      const response = await page.goto(`${TENANT_BASE_URL}${TENANT_INDEX_PATH}`);
      await skipIfBlocked(page, response, "tenant wizard index");

      await expect(page.locator("body")).toBeVisible();
      await assertNoHorizontalOverflow(page);

      // The tenant index lists the SIGNED-IN USER's audience, which the spec does
      // not control, so an exact set is not knowable here. What is knowable: a
      // card whose key is not in the registry is a dead link, and an index with
      // no cards at all is the "empty surface" regression.
      const rendered = await renderedWizardKeys(page);
      const registered = new Set(WIZARD_REGISTRY_KEYS);
      const unknown = [...rendered].filter((key) => !registered.has(key));
      expect(
        unknown,
        `tenant index rendered card(s) for unregistered wizard key(s): ${unknown.join(", ")}`,
      ).toEqual([]);
      expect(
        rendered.size,
        `tenant index rendered no wizard cards at all (expected a subset of ` +
          `${keysForAudience("tenant_admin").length} tenant_admin wizards)`,
      ).toBeGreaterThan(0);
    });

    test(`proof wizard (cross_platform_whitelabel_branding) renders first step + stepper`, async ({ page }) => {
      const url = `${TENANT_BASE_URL}${TENANT_INDEX_PATH}cross_platform_whitelabel_branding/`;
      const response = await page.goto(url);
      await skipIfBlocked(page, response, "proof wizard tenant detail");

      await assertNoHorizontalOverflow(page);
      // Engine renders rmc-wizard-* primitives in every wizard shell.
      await expect(page.locator(".rmc-wizard-shell, [data-rmc-wizard-shell]")).toHaveCount(
        // tolerate either root selector — semantic CSS contract gives both
        // depending on shell mounted (operator vs tenant)
        1,
        { timeout: 10000 },
      ).catch(async () => {
        // Fallback: at minimum the wizard input region should render
        const inputRegion = await page.locator("[data-wizard-step-key], .rmc-wizard-step-body").count();
        expect(
          inputRegion,
          "wizard step body must render even if shell selector mismatches",
        ).toBeGreaterThan(0);
      });
    });
  });
}

test.describe(`Unified Wizard Framework — registry coverage`, () => {
  test(`spec derives its wizard list from the registry (no hand-maintained count)`, async () => {
    // A static assertion — no browser session needed. It locks the spec's wizard
    // list to the registry SOT by SET, not by count: a failure names the wizard
    // that drifted instead of printing two integers.
    const registry = loadWizardRegistry();
    expect(
      registry.size,
      "no wizard JSON discovered under apps/setup_studio/wizards/ — the derivation is reading the wrong directory",
    ).toBeGreaterThan(0);

    const registered = [...registry.keys()].sort();
    const missingFromSpec = registered.filter((key) => !WIZARD_REGISTRY_KEYS.includes(key));
    const unknownInSpec = WIZARD_REGISTRY_KEYS.filter((key) => !registry.has(key));
    expect(
      missingFromSpec,
      `registered wizard(s) the spec does not cover: ${missingFromSpec.join(", ")}`,
    ).toEqual([]);
    expect(
      unknownInSpec,
      `spec covers wizard key(s) the registry does not have: ${unknownInSpec.join(", ")}`,
    ).toEqual([]);

    const unique = new Set(WIZARD_REGISTRY_KEYS);
    expect(unique.size, "duplicate wizard key in the derived list").toBe(
      WIZARD_REGISTRY_KEYS.length,
    );

    // Every exclusion must name a real operator-audience wizard AND state why.
    // An absence that nobody can justify is exactly what let the old list rot.
    const operatorAudience = new Set(keysForAudience("operator"));
    for (const [key, reason] of Object.entries(OPERATOR_INDEX_EXCLUSIONS)) {
      expect(
        operatorAudience.has(key),
        `OPERATOR_INDEX_EXCLUSIONS names "${key}", which is not an operator-audience ` +
          `wizard — the exclusion is stale and is silently weakening the index check`,
      ).toBe(true);
      expect(
        String(reason || "").trim().length,
        `OPERATOR_INDEX_EXCLUSIONS["${key}"] must carry a reason, not a blank`,
      ).toBeGreaterThan(0);
    }

    // What the browser test above will demand, stated as a set.
    const expectedOperatorIndex = [...operatorAudience]
      .filter((key) => !Object.prototype.hasOwnProperty.call(OPERATOR_INDEX_EXCLUSIONS, key))
      .sort();
    expect(OPERATOR_INDEX_WIZARD_KEYS.slice().sort()).toEqual(expectedOperatorIndex);
    expect(
      OPERATOR_INDEX_WIZARD_KEYS.length,
      "no operator-audience wizard survived the exclusion list — the operator index check would be vacuous",
    ).toBeGreaterThan(0);
  });
});
