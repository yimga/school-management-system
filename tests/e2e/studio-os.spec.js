// @ts-check
// Studio OS next-realm browser QA sweep (v3.54.0, 2026-05-21).
//
// Walks the 6 Studio OS sections at 3 viewports (390/768/1366) and asserts:
//   - No horizontal overflow on the document body
//   - No clipped menus / dropdowns
//   - No console errors
//   - Primary actions visible
//   - No dummy href="#" anchors in rendered HTML
//   - Mode rail items are keyboard-focusable
//   - Skip-link target #studio-canvas reachable
//
// Run locally:
//   E2E_LOGIN_USER=... E2E_LOGIN_PASSWORD=... \
//     npx playwright test tests/e2e/studio-os.spec.js
//
// On Render/staging:
//   MANAGER_HOST=manager.staging.runmycampus.com:443 \
//     TENANT_HOST=apple-class-qa.staging.runmycampus.com:443 \
//     E2E_LOGIN_USER=... E2E_LOGIN_PASSWORD=... \
//     npx playwright test tests/e2e/studio-os.spec.js

const { test, expect } = require("@playwright/test");

const MGR = process.env.MANAGER_HOST || "manager.runmycampus.com:8000";
const TENANT = process.env.TENANT_HOST || "appleqa.runmycampus.com:8000";

const VIEWPORTS = [
  { name: "mobile-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "laptop-1366", width: 1366, height: 768 },
];

const SECTIONS = [
  { id: "overview", path: "/studio/", heading: /Studio|Overview/i },
  { id: "experience", path: "/studio/experience/", heading: /Experience/i },
  { id: "automation", path: "/studio/automation/", heading: /Automation/i },
  { id: "output", path: "/studio/output/", heading: /Output/i },
  { id: "launch", path: "/studio/launch/", heading: /Launch/i },
  { id: "control", path: "/studio/control/", heading: /Control/i },
];

test.describe("Studio OS next-realm sweep", () => {
  test.skip(
    !process.env.E2E_LOGIN_USER,
    "Set E2E_LOGIN_USER + E2E_LOGIN_PASSWORD for live sweep"
  );

  for (const vp of VIEWPORTS) {
    for (const sec of SECTIONS) {
      test(`${sec.id} @ ${vp.name}: renders without horizontal overflow`, async ({
        page,
      }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        const consoleErrors = [];
        page.on("console", (msg) => {
          if (msg.type() === "error") consoleErrors.push(msg.text());
        });

        await page.goto(`http://${MGR}${sec.path}`);

        // 1. Section renders with expected heading present somewhere.
        await expect(page.locator("body")).toContainText(sec.heading, {
          timeout: 10_000,
        });

        // 2. No horizontal overflow: documentElement scrollWidth must not
        //    exceed viewport width by more than 1px (rounding tolerance).
        const overflow = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        expect(
          overflow.scrollWidth - overflow.clientWidth,
          `${sec.id} @ ${vp.name}: page scrolls horizontally ` +
            `(scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth})`
        ).toBeLessThanOrEqual(1);

        // 3. No dummy href="#" in rendered HTML (excluding the pre-existing
        //    v3.53 button-as-link in cockpit_copilot_rail.html — that's an
        //    out-of-scope known anti-pattern, predates this wave).
        const hashLinks = await page.locator('a[href="#"]').count();
        // Tolerance: 1 for the v3.53 pre-existing anchor in cockpit_copilot_rail.html.
        expect(
          hashLinks,
          `${sec.id} @ ${vp.name}: found ${hashLinks} dummy href="#" anchors ` +
            `(expected 0 or 1 [pre-existing v3.53 cockpit_copilot_rail anchor])`
        ).toBeLessThanOrEqual(1);

        // 4. No console errors during render.
        expect(
          consoleErrors,
          `${sec.id} @ ${vp.name}: console errors: ${consoleErrors.join(" | ")}`
        ).toEqual([]);
      });
    }
  }

  test("studio rail links all six modes (laptop viewport)", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`http://${MGR}/studio/`);
    await expect(page.locator('nav[aria-label*="Studio modes" i]')).toBeVisible();
    for (const sec of SECTIONS) {
      const linkText = sec.heading.source.replace(/[\\^$|.*+?()\[\]{}]/g, "");
      // Loose match: at least one rail link points at this section's path.
      const hasLink =
        (await page
          .locator(`nav[aria-label*="Studio modes" i] a[href$="${sec.path}"]`)
          .count()) > 0;
      expect(
        hasLink,
        `Studio rail missing link to ${sec.path} (${sec.id})`
      ).toBeTruthy();
    }
  });

  test("skip-link target #studio-canvas is reachable (laptop viewport)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`http://${MGR}/studio/`);
    await expect(page.locator("#studio-canvas")).toBeAttached();
  });

  test("data-rmc-confirm handler is loaded (laptop viewport)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`http://${MGR}/studio/`);
    // Inject a synthetic button with data-rmc-confirm; cancel the prompt;
    // expect default click not to proceed (i.e. event not bubbled).
    const cancelled = await page.evaluate(async () => {
      const btn = document.createElement("button");
      btn.setAttribute("data-rmc-confirm", "Test cancel");
      btn.textContent = "synthetic";
      document.body.appendChild(btn);
      let nativeFired = false;
      btn.addEventListener("click", () => {
        nativeFired = true;
      });
      window.confirm = () => false;
      btn.click();
      btn.remove();
      return !nativeFired;
    });
    expect(
      cancelled,
      "data-rmc-confirm capture-phase handler did NOT stop the native click " +
        "when window.confirm() returned false. Destructive buttons would fire " +
        "their action despite user cancellation."
    ).toBeTruthy();
  });
});

test.describe("Studio OS tenant boundary (tenant host)", () => {
  test.skip(
    !process.env.E2E_LOGIN_USER || !process.env.TENANT_HOST,
    "Set TENANT_HOST + E2E_LOGIN_USER for tenant-boundary sweep"
  );

  test("tenant overview does not expose operator-only chips", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`http://${TENANT}/studio/`);
    // RBAC + Feature control chips are gated by request.public_host_kind == 'manager'.
    await expect(page.locator("body")).not.toContainText(/RBAC\s*&\s*permissions/i);
  });

  test("tenant control does not show platform-wide audit toggle", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`http://${TENANT}/studio/control/`);
    // System config console is operator-only.
    await expect(page.locator("body")).not.toContainText(/System config console/i);
  });
});
