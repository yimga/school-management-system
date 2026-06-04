// Outbox at-rest encryption — exercises the REAL shipped seal/open path in
// static/js/rmc-wal-stream.js (not a re-implementation) against Node WebCrypto
// and a dependency-free in-memory IndexedDB shim. This is the automated half of
// the "browser E2E" gate for SMS_OFFLINE_CONFIG.encryptOutbox: it proves the
// crypto round-trip, the at-rest sealing (no plaintext in the stored row), the
// backward-compatible plaintext passthrough, and graceful handling of an
// undecryptable row. The genuine browser IndexedDB CryptoKey-persistence path
// is covered by tests/e2e/offline-outbox-encryption.spec.js (Playwright).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { webcrypto } from "node:crypto";
import { describe, it, expect, beforeAll } from "vitest";

const SRC = resolve(__dirname, "..", "static", "js", "rmc-wal-stream.js");

// ── Minimal in-memory IndexedDB shim ──────────────────────────────────────
// Implements exactly the surface rmc-wal-stream.js touches: versioned open with
// a one-time upgrade, objectStore get/put, and an index with count()/getAll()
// over an IDBKeyRange.only(...). Records live in plain JS Maps so a stored
// CryptoKey is just an object reference (structured-clone fidelity is the
// browser test's job, not this one's).
function makeIndexedDBShim() {
  const stores: Record<string, { keyPath: string; records: Map<unknown, any>; indexes: Record<string, string> }> = {};
  let created = false;

  const db = {
    objectStoreNames: { contains: (n: string) => n in stores },
    createObjectStore(name: string, opts: { keyPath: string }) {
      stores[name] = { keyPath: opts.keyPath, records: new Map(), indexes: {} };
      return { createIndex(idxName: string, field: string) { stores[name].indexes[idxName] = field; } };
    },
    transaction(names: string | string[]) {
      const tx: any = { oncomplete: null, onerror: null };
      const storeName = Array.isArray(names) ? names[0] : names;
      const store = stores[storeName];
      let pending = 0;
      let settled = false;
      const opEnd = () => {
        pending -= 1;
        if (pending === 0) {
          setTimeout(() => {
            if (pending === 0 && !settled) { settled = true; if (tx.oncomplete) tx.oncomplete(); }
          }, 0);
        }
      };
      const matchRange = (val: unknown, range: any) => (range && "only" in range ? val === range.only : true);
      const os = {
        get(key: unknown) {
          const req: any = { onsuccess: null, onerror: null, result: undefined };
          pending += 1;
          setTimeout(() => { req.result = store.records.get(key); if (req.onsuccess) req.onsuccess(); opEnd(); }, 0);
          return req;
        },
        put(obj: any) {
          const req: any = { onsuccess: null, onerror: null };
          store.records.set(obj[store.keyPath], obj);
          pending += 1;
          setTimeout(() => { if (req.onsuccess) req.onsuccess(); opEnd(); }, 0);
          return req;
        },
        index(idxName: string) {
          const field = store.indexes[idxName];
          return {
            count(range: any) {
              const req: any = { onsuccess: null, result: 0 };
              setTimeout(() => {
                let n = 0;
                for (const v of store.records.values()) if (matchRange(v[field], range)) n += 1;
                req.result = n; if (req.onsuccess) req.onsuccess();
              }, 0);
              return req;
            },
            getAll(range: any) {
              const req: any = { onsuccess: null, result: [] };
              setTimeout(() => {
                const out: any[] = [];
                for (const v of store.records.values()) if (matchRange(v[field], range)) out.push(v);
                req.result = out; if (req.onsuccess) req.onsuccess();
              }, 0);
              return req;
            },
          };
        },
      };
      tx.objectStore = () => os;
      return tx;
    },
  };

  const indexedDB = {
    open() {
      const req: any = { onupgradeneeded: null, onsuccess: null, onerror: null, result: db };
      setTimeout(() => {
        if (!created) { created = true; if (req.onupgradeneeded) req.onupgradeneeded(); }
        if (req.onsuccess) req.onsuccess();
      }, 0);
      return req;
    },
  };
  return { indexedDB, dump: (name: string) => Array.from(stores[name]?.records.values() ?? []) };
}

class WebSocketStub {
  static OPEN = 1;
  static CONNECTING = 0;
  readyState = 0;
  onopen: any = null; onmessage: any = null; onclose: any = null; onerror: any = null;
  send() {}
  close() {}
}

let shimDump: (name: string) => any[];

beforeAll(() => {
  if (!(globalThis as any).crypto || !(globalThis as any).crypto.subtle) {
    (globalThis as any).crypto = webcrypto;
  }
  const w = globalThis as any;
  const shim = makeIndexedDBShim();
  shimDump = shim.dump;
  w.indexedDB = shim.indexedDB;
  w.IDBKeyRange = { only: (v: unknown) => ({ only: v }) };
  w.WebSocket = WebSocketStub;
  w.window.indexedDB = shim.indexedDB;
  w.window.IDBKeyRange = w.IDBKeyRange;
  w.window.WebSocket = WebSocketStub;
  w.window.__RMC_OUTBOX_TEST__ = true;
  w.window.SMS_OFFLINE_CONFIG = { encryptOutbox: true };
  if (!w.window.crypto || !w.window.crypto.subtle) w.window.crypto = w.crypto;

  const src = readFileSync(SRC, "utf8");
  // Indirect eval runs in global scope so `window.rmcWAL = ...` lands on the
  // jsdom global window.
  // eslint-disable-next-line no-eval
  (0, eval)(src);
});

const T = () => (globalThis as any).window.rmcWAL.__test;

describe("offline outbox at-rest encryption (real rmc-wal-stream.js)", () => {
  it("exposes the test hook only because __RMC_OUTBOX_TEST__ is set", () => {
    expect((globalThis as any).window.rmcWAL).toBeTruthy();
    expect(T()).toBeTruthy();
    expect(T().encEnabled()).toBe(true);
  });

  it("seals then opens an actions array back to the original (round-trip)", async () => {
    const actions = [{ recipient_id: 5, subject: "s", body: "hello", locale_target: "fr" }];
    const sealed = await T().sealActions(actions);
    expect(sealed.iv).toBeTruthy();
    expect(sealed.ct).toBeTruthy();
    expect(JSON.stringify(sealed)).not.toContain("hello");
    const opened = await T().openActions({ actions_sealed: sealed });
    expect(opened).toEqual(actions);
  });

  it("append() stores a sealed row with NO plaintext at rest", async () => {
    const txnId = await (globalThis as any).window.rmcWAL.append("communication_send", [
      { recipient_id: 9, subject: "subj", body: "TOP-SECRET-BODY" },
    ]);
    expect(txnId).toBeTruthy();
    const rows = shimDump("outbox");
    const row = rows.find((r) => r.txn_id === txnId);
    expect(row).toBeTruthy();
    expect(row.actions).toBeUndefined();
    expect(row.actions_sealed).toBeTruthy();
    expect(JSON.stringify(row)).not.toContain("TOP-SECRET-BODY");
    // …and the sealed row is still recoverable on flush.
    const opened = await T().openActions(row);
    expect(opened[0].body).toBe("TOP-SECRET-BODY");
  });

  it("opens a legacy plaintext row unchanged (backward compatible)", async () => {
    const plain = [{ recipient_id: 1, body: "legacy" }];
    const opened = await T().openActions({ actions: plain });
    expect(opened).toEqual(plain);
  });

  it("returns [] for an undecryptable sealed row so flush skips it", async () => {
    const opened = await T().openActions({ actions_sealed: { iv: btoa("000000000000"), ct: btoa("garbage-bytes") } });
    expect(opened).toEqual([]);
  });
});

describe("offline outbox eviction plan (real rmc-wal-stream.js)", () => {
  const NOW = 1_000_000_000_000;

  it("drops acked rows past retention but keeps fresh acked", () => {
    const t = T();
    const rows = [
      { txn_id: "a", status: "acked", acked_at: NOW - t.ACKED_RETENTION_MS - 1 },
      { txn_id: "b", status: "acked", acked_at: NOW - 1000 },
      { txn_id: "c", status: "acked" }, // no acked_at -> drop
    ];
    const { toDelete } = t.evictionPlan(rows, NOW, 500);
    expect(toDelete).toContain("a");
    expect(toDelete).toContain("c");
    expect(toDelete).not.toContain("b");
  });

  it("ages out unsynced rows older than the 30d ceiling", () => {
    const t = T();
    const rows = [
      { txn_id: "old", status: "queued", created_at: NOW - t.MAX_OUTBOX_AGE_MS - 1 },
      { txn_id: "new", status: "queued", created_at: NOW - 1000 },
    ];
    const { toDelete, cappedOverflow } = t.evictionPlan(rows, NOW, 500);
    expect(toDelete).toEqual(["old"]);
    expect(cappedOverflow).toBe(0);
  });

  it("caps the backlog by evicting the OLDEST unsynced rows", () => {
    const t = T();
    const rows = [];
    for (let i = 0; i < 5; i++) {
      rows.push({ txn_id: "q" + i, status: "queued", created_at: NOW - (5 - i) * 1000 });
    }
    const { toDelete, cappedOverflow } = t.evictionPlan(rows, NOW, 3);
    expect(cappedOverflow).toBe(2);
    expect(toDelete).toContain("q0"); // oldest
    expect(toDelete).toContain("q1");
    expect(toDelete).not.toContain("q4"); // newest survives
  });

  it("keeps everything when under cap and fresh", () => {
    const t = T();
    const rows = [{ txn_id: "x", status: "queued", created_at: NOW - 1000 }];
    const { toDelete } = t.evictionPlan(rows, NOW, 500);
    expect(toDelete).toEqual([]);
  });
});
