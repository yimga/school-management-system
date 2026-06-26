// @ts-check
const { test, expect } = require('@playwright/test');

const TENANT_SLUG = process.env.E2E_TENANT_SLUG || 'demo-school';
const BASE =
  process.env.E2E_TENANT_BASE_URL ||
  process.env.PLAYWRIGHT_BASE_URL ||
  `http://${TENANT_SLUG}.runmycampus.com:8000`;

function loginPath() {
  return `/t/${TENANT_SLUG}/authentication/login/`;
}

test.describe('Immersive login canvas', () => {
  test('role gateway change-role round trip', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE}${loginPath()}`, { waitUntil: 'domcontentloaded' });

    const immersive = page.locator('[data-rmc-auth-immersive]');
    await expect(immersive).toBeVisible();

    const staff = page.locator("[data-rmc-auth-role='staff']");
    await expect(staff).toBeVisible();
    await staff.click();

    await expect(page.locator("[data-rmc-auth-step='creds'].is-on")).toBeVisible();
    const back = page.locator('[data-rmc-auth-back]');
    await expect(back).toHaveCount(1);
    await back.click();

    await expect(page.locator("[data-rmc-auth-step='role'].is-on")).toBeVisible();
  });

  test('desktop shell fits viewport without document scroll', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`${BASE}${loginPath()}`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() =>
      document.body.classList.contains('rmc-auth-immersive-doc-lock')
    );

    const metrics = await page.evaluate(() => {
      const immersive = document.querySelector("[data-rmc-auth-immersive]");
      const glass = document.querySelector(".rmc-auth-immersive__glass");
      const immersiveBox = immersive ? immersive.getBoundingClientRect() : null;
      const glassBox = glass ? glass.getBoundingClientRect() : null;
      return {
        docScroll: document.documentElement.scrollHeight - window.innerHeight,
        immersiveWidth: immersiveBox ? immersiveBox.width : 0,
        glassWidth: glassBox ? glassBox.width : 0,
        shellOff: document.documentElement.getAttribute("data-rmc-shell"),
      };
    });
    expect(metrics.docScroll).toBeLessThanOrEqual(2);
    expect(metrics.shellOff).toBe("off");
    expect(metrics.immersiveWidth).toBeGreaterThan(900);
    expect(metrics.glassWidth).toBeGreaterThan(280);
  });

  test('mobile shows brand strip above sign-in card', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${BASE}${loginPath()}`, { waitUntil: 'domcontentloaded' });

    const strip = page.locator('[data-rmc-login-mobile-strip]');
    await expect(strip).toBeVisible();
    await expect(page.locator('[data-rmc-login-canvas]')).toBeHidden();
    await expect(page.locator('[data-rmc-auth-immersive] .rmc-auth-immersive__glass')).toBeVisible();
  });
});
