// @ts-check
/**
 * Browser E2E gate for the offline outbox at-rest encryption
 * (SMS_OFFLINE_CONFIG.encryptOutbox). This is the half the vitest unit test
 * cannot cover: real Chromium IndexedDB persistence of a non-extractable
 * AES-GCM CryptoKey + real Web Crypto, on a real HTTP origin.
 *
 * It loads the actual shipped static/js/rmc-wal-stream.js into a real page
 * (so we test production code, not a copy), enables encryption via the test
 * hook, appends a message through window.rmcWAL.append(), then asserts:
 *   1. the row persisted in IndexedDB carries `actions_sealed` and NO plaintext;
 *   2. the sealed payload round-trips back to the original via openActions();
 *   3. a fresh page (CryptoKey reloaded from IndexedDB) still decrypts it.
 *
 * Run with the dev server up (the page just needs a same-origin 200 so
 * IndexedDB is allowed — opaque about:blank origins block IndexedDB):
 *     BASE_URL=http://127.0.0.1:8000 npx playwright test tests/e2e/offline-outbox-encryption.spec.js
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
test.use({ baseURL: BASE_URL });

const WAL_SRC = fs.readFileSync(
  path.resolve(__dirname, '..', '..', 'static', 'js', 'rmc-wal-stream.js'),
  'utf8'
);

const SECRET = 'TOP-SECRET-PLAINTEXT-BODY';

async function bootWalWithEncryption(page) {
  // Arm the test hook + encryption BEFORE the script runs.
  await page.addInitScript(() => {
    // @ts-ignore
    window.__RMC_OUTBOX_TEST__ = true;
    // @ts-ignore
    window.SMS_OFFLINE_CONFIG = { encryptOutbox: true };
  });
  // Any same-origin 200 page gives us a real HTTP origin for IndexedDB.
  await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.addScriptTag({ content: WAL_SRC });
  await page.waitForFunction(() => !!(window.rmcWAL && window.rmcWAL.__test));
}

test('outbox encrypts at rest and round-trips in a real browser', async ({ page }) => {
  await bootWalWithEncryption(page);

  const result = await page.evaluate(async (secret) => {
    const txnId = await window.rmcWAL.append('communication_send', [
      { recipient_id: 42, subject: 'subj', body: secret },
    ]);
    // Read the raw stored row straight out of IndexedDB.
    const row = await new Promise((resolve, reject) => {
      const req = indexedDB.open('rmc_wal_v4', 1);
      req.onsuccess = () => {
        const db = req.result;
        const tx = db.transaction('outbox', 'readonly');
        const rq = tx.objectStore('outbox').get(txnId);
        rq.onsuccess = () => resolve(rq.result);
        rq.onerror = () => reject(rq.error);
      };
      req.onerror = () => reject(req.error);
    });
    const opened = await window.rmcWAL.__test.openActions(row);
    return {
      hasSealed: !!row.actions_sealed,
      hasPlaintext: row.actions !== undefined,
      rawHasSecret: JSON.stringify(row).indexOf(secret) !== -1,
      openedBody: opened && opened[0] && opened[0].body,
    };
  }, SECRET);

  expect(result.hasSealed).toBe(true);
  expect(result.hasPlaintext).toBe(false);
  expect(result.rawHasSecret).toBe(false);
  expect(result.openedBody).toBe(SECRET);
});

test('a reloaded page decrypts the persisted CryptoKey', async ({ page }) => {
  await bootWalWithEncryption(page);
  const txnId = await page.evaluate(async (secret) => {
    return window.rmcWAL.append('communication_send', [
      { recipient_id: 7, subject: 's', body: secret },
    ]);
  }, SECRET);

  // Reload — the AES key must be re-read from IndexedDB, not regenerated.
  await bootWalWithEncryption(page);
  const openedBody = await page.evaluate(async (id) => {
    const row = await new Promise((resolve, reject) => {
      const req = indexedDB.open('rmc_wal_v4', 1);
      req.onsuccess = () => {
        const tx = req.result.transaction('outbox', 'readonly');
        const rq = tx.objectStore('outbox').get(id);
        rq.onsuccess = () => resolve(rq.result);
        rq.onerror = () => reject(rq.error);
      };
      req.onerror = () => reject(req.error);
    });
    const opened = await window.rmcWAL.__test.openActions(row);
    return opened && opened[0] && opened[0].body;
  }, txnId);

  expect(openedBody).toBe(SECRET);
});
