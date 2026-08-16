// @ts-check
const { test, expect } = require('@playwright/test');

const TENANT_SLUG = process.env.E2E_TENANT_SLUG || 'demo-school';
const BASE =
  process.env.E2E_TENANT_BASE_URL ||
  process.env.PLAYWRIGHT_BASE_URL ||
  `http://127.0.0.1:${process.env.VISUAL_QA_TENANT_PHASE_PORT || '8013'}`;

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

  test('approved V3 uses a tight composed seam and balanced school pulse', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto(`${BASE}${loginPath()}`, { waitUntil: 'domcontentloaded' });

    const layout = await page.evaluate(() => {
      const canvas = document.querySelector('[data-rmc-login-canvas]');
      const auth = document.querySelector('.rmc-auth-immersive__auth');
      const hero = document.querySelector('.rmc-auth-immersive__carousel');
      const pulse = document.querySelector('.rmc-auth-immersive__dash');
      const bento = document.querySelector('.rmc-auth-immersive__bento');
      const canvasBox = canvas?.getBoundingClientRect();
      const authBox = auth?.getBoundingClientRect();
      const heroBox = hero?.getBoundingClientRect();
      const pulseBox = pulse?.getBoundingClientRect();
      const bentoBox = bento?.getBoundingClientRect();
      return {
        seam: canvasBox && authBox ? authBox.left - canvasBox.right : 999,
        heroAndPulseShareRow:
          !!heroBox && !!pulseBox && Math.abs(heroBox.top - pulseBox.top) < 90,
        bentoSpansStory:
          !!bentoBox && !!canvasBox && bentoBox.width > canvasBox.width * 0.75,
      };
    });
    expect(layout.seam).toBeLessThanOrEqual(24);
    expect(layout.heroAndPulseShareRow).toBe(true);
    expect(layout.bentoSpansStory).toBe(true);
    await expect(page.getByText('Welcome back')).toBeVisible();
    await expect(page.locator('.rmc-auth-immersive__recommended')).toBeVisible();
    await expect(page.locator('[data-rmc-local-state]')).toBeVisible();
  });

  test('school pulse keeps announcements and the local partner placement visible', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto(`${BASE}${loginPath()}`, { waitUntil: 'domcontentloaded' });

    const pulse = page.locator('.rmc-auth-immersive__dash');
    const announcements = pulse.getByText('Announcements', { exact: true });
    const partner = pulse.locator('[data-rmc-sponsored-region]');
    await expect(pulse).toBeVisible();
    await expect(announcements).toBeVisible();
    await expect(partner).toBeVisible();

    const containment = await page.evaluate(() => {
      const pulse = document.querySelector('.rmc-auth-immersive__dash');
      const announcement = Array.from(pulse?.querySelectorAll('b') || [])
        .find((node) => node.textContent?.trim() === 'Announcements');
      const partner = pulse?.querySelector('[data-rmc-sponsored-region]');
      const pulseBox = pulse?.getBoundingClientRect();
      const announcementBox = announcement?.getBoundingClientRect();
      const partnerBox = partner?.getBoundingClientRect();
      return {
        announcementInside: !!pulseBox && !!announcementBox && announcementBox.bottom <= pulseBox.bottom + 1,
        partnerInside: !!pulseBox && !!partnerBox && partnerBox.bottom <= pulseBox.bottom + 1,
      };
    });
    expect(containment.announcementInside).toBe(true);
    expect(containment.partnerInside).toBe(true);
  });

  test('extreme-short desktop keeps hero copy and credential entry reachable', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 354 });
    await page.goto(`${BASE}${loginPath()}`, { waitUntil: 'domcontentloaded' });
    const hero = page.locator('[data-rmc-auth-carousel-slide].is-on');
    await expect(hero).toBeVisible();
    const box = await hero.boundingBox();
    expect(box).not.toBeNull();
    expect(box.height).toBeGreaterThan(45);
    await page.locator("[data-rmc-auth-role='staff']").click();
    await expect(page.locator('#login-username')).toBeVisible();
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
