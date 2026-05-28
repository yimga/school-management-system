// @ts-check
/**
 * Manager host: bulk list <dialog> confirm flow (schools fleet + operator team).
 * Requires Django on manager host with visual QA credentials (see run_manager_bulk_confirm_e2e.sh).
 */
const { test, expect } = require('@playwright/test');
const {
  AUTH_STATE_PATH,
  ensureManagerHost,
} = require('./helpers/manager-login');

const MANAGER_HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const MANAGER_PORT = process.env.VISUAL_QA_PORT || '8000';
const MANAGER_BASE_URL =
  process.env.MANAGER_BASE_URL ||
  process.env.BASE_URL ||
  `http://${MANAGER_HOST}:${MANAGER_PORT}`;

const SCHOOLS_PATH = '/super/schools/';
const TEAM_PATH = '/super/team/';
const BULK_SCHOOLS_API = '**/super/api/bulk/schools/**';

/** @param {import('@playwright/test').Page} page */
async function gotoSchoolsList(page) {
  const response = await page.goto(SCHOOLS_PATH, {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await ensureManagerHost(page);
  expect(response?.status(), SCHOOLS_PATH).toBeLessThan(400);
  const table = page.locator('table[data-rmc-list-bulk="1"]');
  await expect(table).toBeVisible({ timeout: 30000 });
  return table;
}

/** @param {import('@playwright/test').Page} page */
async function gotoTeamRoster(page) {
  const response = await page.goto(TEAM_PATH, {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await ensureManagerHost(page);
  expect(response?.status(), TEAM_PATH).toBeLessThan(400);
  const table = page.locator('table[data-rmc-list-bulk="1"]');
  await expect(table).toBeVisible({ timeout: 30000 });
  return table;
}

/** Prefer seeded peer row; fall back to first bulk checkbox. */
async function selectTeamBulkTargetRow(page, table) {
  const peerRow = table.locator('tbody tr', {
    has: page.getByText('e2e_bulk_operator_peer', { exact: false }),
  });
  const peerCb = peerRow.locator('[data-rmc-bulk-row]').first();
  const rowCb =
    (await peerCb.count()) > 0
      ? peerCb
      : table.locator('tbody [data-rmc-bulk-row]').first();
  await expect(rowCb).toBeVisible({ timeout: 15000 });
  await checkBulkRow(rowCb);
  const barId = await table.getAttribute('data-rmc-bulk-bar-id');
  const bar = barId
    ? page.locator(`[data-rmc-list-bulk-bar][data-rmc-bulk-bar-for="${barId}"]`)
    : page.locator('[data-rmc-list-bulk-bar]').first();
  await expect(bar).toBeVisible({ timeout: 15000 });
  await expect(bar.locator('[data-rmc-bulk-count]')).toContainText(/[1-9]\d* selected/);
  return { rowCb, bar };
}

/** @param {import('@playwright/test').Locator} rowCb */
async function checkBulkRow(rowCb) {
  await rowCb.evaluate((el) => {
    el.checked = true;
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

/** @param {import('@playwright/test').Page} page @param {import('@playwright/test').Locator} table */
async function selectFirstBulkRow(page, table) {
  const rowCb = table.locator('tbody [data-rmc-bulk-row]').first();
  await expect(rowCb).toBeVisible({ timeout: 15000 });
  await checkBulkRow(rowCb);
  const barId = await table.getAttribute('data-rmc-bulk-bar-id');
  const bar = barId
    ? page.locator(`[data-rmc-list-bulk-bar][data-rmc-bulk-bar-for="${barId}"]`)
    : page.locator('[data-rmc-list-bulk-bar]').first();
  await expect(bar).toBeVisible({ timeout: 15000 });
  await expect(bar.locator('[data-rmc-bulk-count]')).toContainText(/[1-9]\d* selected/);
  return { rowCb, bar };
}

/** @param {import('@playwright/test').Locator} dlg */
async function expectConfirmDialogOpen(dlg) {
  await expect(dlg).toBeVisible();
}

/** @param {import('@playwright/test').Locator} dlg */
async function expectConfirmDialogClosed(dlg) {
  await expect(dlg).toBeHidden();
}

/** @param {import('@playwright/test').Locator} bar @param {RegExp} name */
async function clickBulkBarAction(bar, name) {
  const btn = bar.getByRole('button', { name });
  await expect(btn).toBeVisible({ timeout: 15000 });
  await btn.scrollIntoViewIfNeeded();
  await btn.evaluate((el) => {
    el.click();
  });
}

/** @param {import('@playwright/test').Page} page */
function confirmDialog(page) {
  return page.locator('[data-rmc-bulk-confirm-dialog]');
}

/** @param {import('@playwright/test').Page} page */
async function bulkActionsFromTable(page) {
  const raw = await page
    .locator('table[data-rmc-list-bulk="1"]')
    .getAttribute('data-rmc-bulk-actions');
  return raw ? JSON.parse(raw) : [];
}

test.use({
  baseURL: MANAGER_BASE_URL,
  viewport: { width: 1400, height: 900 },
  storageState: AUTH_STATE_PATH,
});

test.describe('manager bulk confirm dialog (authenticated)', () => {
  test.describe.configure({ mode: 'serial', timeout: 120000 });

  test.beforeEach(async ({ page }) => {
    await ensureManagerHost(page);
  });

  test('schools list exposes confirm dialog and excludes apply_purge from bulk actions', async ({
    page,
  }) => {
    await gotoSchoolsList(page);
    await expect(confirmDialog(page)).toBeAttached();
    const actions = await bulkActionsFromTable(page);
    expect(actions.length).toBeGreaterThan(0);
    const actionIds = actions.map((a) => a.action || a.id).filter(Boolean);
    expect(actionIds).not.toContain('apply_purge');
    expect(actionIds).not.toContain('purge');
    const postActions = actions.filter((a) => a.kind === 'post');
    for (const act of postActions) {
      expect(String(act.action || '')).not.toMatch(/apply_purge/i);
    }
  });

  test('selecting a row shows bulk bar and opens dialog on Unfreeze', async ({ page }) => {
    const table = await gotoSchoolsList(page);
    const { bar } = await selectFirstBulkRow(page, table);
    await clickBulkBarAction(bar, /^Unfreeze$/i);
    const dlg = confirmDialog(page);
    await expectConfirmDialogOpen(dlg);
    await expect(dlg.locator('[data-rmc-bulk-confirm-message]')).not.toBeEmpty();
    await dlg.locator('[data-rmc-bulk-confirm-cancel]').click();
    await expectConfirmDialogClosed(dlg);
  });

  test('cancel does not POST to bulk schools API', async ({ page }) => {
    let postCount = 0;
    await page.route(BULK_SCHOOLS_API, async (route) => {
      if (route.request().method() === 'POST') {
        postCount += 1;
      }
      await route.continue();
    });
    const table = await gotoSchoolsList(page);
    const { bar } = await selectFirstBulkRow(page, table);
    await clickBulkBarAction(bar, /^Unfreeze$/i);
    const dlg = confirmDialog(page);
    await expectConfirmDialogOpen(dlg);
    await dlg.locator('[data-rmc-bulk-confirm-cancel]').click();
    await page.waitForTimeout(400);
    expect(postCount).toBe(0);
  });

  test('phrase-gated Purge dry-run keeps submit disabled until phrase matches', async ({
    page,
  }) => {
    const table = await gotoSchoolsList(page);
    const { bar } = await selectFirstBulkRow(page, table);
    await clickBulkBarAction(bar, /Purge dry-run/i);
    const dlg = confirmDialog(page);
    await expectConfirmDialogOpen(dlg);
    const submit = dlg.locator('[data-rmc-bulk-confirm-submit]');
    const phraseInput = dlg.locator('[data-rmc-bulk-confirm-phrase-input]');
    await expect(submit).toBeDisabled();
    await phraseInput.fill('DRY RUN PUR');
    await expect(submit).toBeDisabled();
    await phraseInput.fill('DRY RUN PURGE');
    await expect(submit).toBeEnabled();
    await dlg.locator('[data-rmc-bulk-confirm-cancel]').click();
  });

  test('confirmed Unfreeze POSTs JSON with ids and action (mocked)', async ({ page }) => {
    /** @type {Record<string, unknown> | null} */
    let capturedBody = null;
    await page.route(BULK_SCHOOLS_API, async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      capturedBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          processed: 1,
          succeeded: 1,
          results: [{ ok: true, id: capturedBody?.ids?.[0] }],
        }),
      });
    });

    const table = await gotoSchoolsList(page);
    const rowCb = table.locator('tbody [data-rmc-bulk-row]').first();
    const schoolId = await rowCb.getAttribute('value');
    await checkBulkRow(rowCb);
    const barId = await table.getAttribute('data-rmc-bulk-bar-id');
    const bar = barId
      ? page.locator(`[data-rmc-list-bulk-bar][data-rmc-bulk-bar-for="${barId}"]`)
      : page.locator('[data-rmc-list-bulk-bar]').first();
    await expect(bar).toBeVisible({ timeout: 15000 });
    await clickBulkBarAction(bar, /^Unfreeze$/i);
    const dlg = confirmDialog(page);
    await expect(dlg.locator('[data-rmc-bulk-confirm-submit]')).toBeEnabled();
    await dlg.locator('form[data-rmc-confirm-dialog]').evaluate((form) => {
      form.requestSubmit();
    });

    await expect.poll(() => capturedBody).not.toBeNull();
    expect(capturedBody.action).toBe('unfreeze');
    expect(capturedBody.ids).toEqual([schoolId]);
    await expectConfirmDialogClosed(dlg);
  });

  test('operator team roster opens confirm dialog on Suspend when manageable', async ({
    page,
  }) => {
    const table = await gotoTeamRoster(page);
    const actions = await bulkActionsFromTable(page);
    const suspendAction = actions.find(
      (a) => a.action === 'suspend' || a.id === 'suspend',
    );
    expect(suspendAction, 'team roster must expose Suspend bulk action').toBeTruthy();
    const { bar } = await selectTeamBulkTargetRow(page, table);
    await clickBulkBarAction(bar, /^Suspend$/i);
    const dlg = confirmDialog(page);
    await expectConfirmDialogOpen(dlg);
    await dlg.locator('[data-rmc-bulk-confirm-cancel]').click();
    await expectConfirmDialogClosed(dlg);
  });
});
