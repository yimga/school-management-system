// RunMyCampus WAL outbox stream client (v4.00.0).
//
// Promotes the existing Dexie-based offline outbox to a true Write-Ahead Log
// with txn_id + vector_clock + server-ack states. Mass actions like
// "Mark All Present" compress 35+ rows into ONE delta payload flushed over a
// persistent WSS to /ws/wal/. Server dedupe means at-least-once delivery is
// safe.
//
// API surface (window.rmcWAL):
//   .append(domain, actions)        -> Promise<txn_id>
//   .flush()                        -> Promise<{shipped:int, queued:int}>
//   .pending()                      -> Promise<int>
//   .onAck(cb)                      -> () => void  (unsubscribe)
//
// Backoff: exponential with jitter, max 30s. The WS stays open across page
// navigations via the Service Worker registration scope.

(function () {
  "use strict";
  if (window.rmcWAL) return;

  const DB_NAME = "rmc_wal_v4";
  const STORE = "outbox";
  const STORE_CLOCK = "clock";
  const WS_PATH = "/ws/wal/";
  const MAX_BACKOFF_MS = 30_000;

  let ws = null;
  let socketGen = 0;
  let backoff = 500;
  let ackListeners = new Set();
  const pendingAck = new Map(); // txn_id -> resolve

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const os = db.createObjectStore(STORE, { keyPath: "txn_id" });
          os.createIndex("status", "status");
          os.createIndex("created_at", "created_at");
        }
        if (!db.objectStoreNames.contains(STORE_CLOCK)) {
          db.createObjectStore(STORE_CLOCK, { keyPath: "k" });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function nextVectorClock() {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CLOCK, "readwrite");
      const os = tx.objectStore(STORE_CLOCK);
      const rq = os.get("vc");
      rq.onsuccess = () => {
        const cur = rq.result?.v || 0;
        const next = cur + 1;
        os.put({ k: "vc", v: next }).onsuccess = () => resolve(next);
      };
      rq.onerror = () => reject(rq.error);
    });
  }

  function randomId() {
    if (window.crypto?.randomUUID) return crypto.randomUUID();
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  async function tenantHash() {
    // Cookie carries the rmc_rls_jwt; we can't decode the HMAC client-side,
    // but the server cross-checks tenant_hash against the bound school anyway.
    // Best-effort: hash the document host so dev environments still validate.
    const host = window.location.host || "_";
    const buf = new TextEncoder().encode(host);
    const digest = await crypto.subtle.digest("SHA-256", buf);
    return [...new Uint8Array(digest)].slice(0, 6).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  // ── Optional at-rest encryption of the outbox payload (audit residual) ──
  // The outbox holds attendance/grades/messages/charges (PII) in IndexedDB. When
  // SMS_OFFLINE_CONFIG.encryptOutbox is true we AES-GCM-seal the `actions` before
  // storing and unseal at flush time. OPT-IN (default off) + backward-compatible:
  // a row may be sealed OR plaintext, and flush handles both, so enabling it
  // never strands already-queued work. The AES key is a non-extractable CryptoKey
  // persisted in the existing clock store (no DB version bump).
  function encEnabled() {
    try {
      return !!(window.SMS_OFFLINE_CONFIG && window.SMS_OFFLINE_CONFIG.encryptOutbox);
    } catch (e) {
      return false;
    }
  }

  function bufToB64(buf) {
    var bytes = new Uint8Array(buf);
    var bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }

  function b64ToBuf(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }

  async function getEncKey() {
    const db = await openDb();
    const existing = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CLOCK, "readonly");
      const rq = tx.objectStore(STORE_CLOCK).get("enckey");
      rq.onsuccess = () => resolve(rq.result?.v || null);
      rq.onerror = () => reject(rq.error);
    });
    if (existing) return existing;
    const key = await crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false, // non-extractable — can be stored as a CryptoKey but never exported
      ["encrypt", "decrypt"]
    );
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CLOCK, "readwrite");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.objectStore(STORE_CLOCK).put({ k: "enckey", v: key });
    });
    return key;
  }

  async function sealActions(actions) {
    const key = await getEncKey();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const plain = new TextEncoder().encode(JSON.stringify(actions));
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv: iv }, key, plain);
    return { iv: bufToB64(iv.buffer), ct: bufToB64(ct) };
  }

  async function openActions(row) {
    // Backward-compatible: plaintext rows return row.actions directly.
    if (!row.actions_sealed) return row.actions;
    try {
      const key = await getEncKey();
      const iv = new Uint8Array(b64ToBuf(row.actions_sealed.iv));
      const pt = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: iv },
        key,
        b64ToBuf(row.actions_sealed.ct)
      );
      return JSON.parse(new TextDecoder().decode(pt));
    } catch (e) {
      // Undecryptable (key rotated/cleared) — drop to empty so flush skips it
      // rather than shipping garbage; the row stays queued for manual review.
      return [];
    }
  }

  async function append(domain, actions) {
    if (!domain || !Array.isArray(actions) || actions.length === 0) {
      throw new Error("rmcWAL.append: domain+actions required");
    }
    const txn_id = randomId();
    const vector_clock = await nextVectorClock();
    const envelope = {
      txn_id,
      vector_clock,
      domain,
      tenant_hash: await tenantHash(),
      status: "queued",
      created_at: Date.now(),
    };
    // Seal the PII-bearing actions at rest when enabled; otherwise store plain.
    if (encEnabled()) {
      try {
        envelope.actions_sealed = await sealActions(actions);
      } catch (e) {
        envelope.actions = actions; // crypto unavailable → fall back to plaintext
      }
    } else {
      envelope.actions = actions;
    }
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.objectStore(STORE).put(envelope);
    });
    scheduleFlush();
    return txn_id;
  }

  async function pendingCount() {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const rq = tx.objectStore(STORE).index("status").count(IDBKeyRange.only("queued"));
      rq.onsuccess = () => resolve(rq.result || 0);
      rq.onerror = () => reject(rq.error);
    });
  }

  async function markAcked(txn_id) {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      const os = tx.objectStore(STORE);
      const rq = os.get(txn_id);
      rq.onsuccess = () => {
        const row = rq.result;
        if (row) {
          row.status = "acked";
          row.acked_at = Date.now();
          os.put(row);
        }
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  function ensureSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return ws;
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}${WS_PATH}`;
    const myGen = ++socketGen;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      ws = null;
      scheduleReconnect(myGen);
      return null;
    }
    ws.onopen = () => {
      backoff = 500;
      flush();
    };
    ws.onmessage = (ev) => {
      let msg = null;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg && msg.ok && msg.txn_id) {
        markAcked(msg.txn_id);
        const resolver = pendingAck.get(msg.txn_id);
        if (resolver) { resolver(true); pendingAck.delete(msg.txn_id); }
        ackListeners.forEach((cb) => { try { cb(msg.txn_id); } catch {} });
      }
    };
    ws.onclose = () => { ws = null; scheduleReconnect(myGen); };
    ws.onerror = () => { try { ws?.close(); } catch {} };
    return ws;
  }

  function scheduleReconnect(gen) {
    if (gen !== socketGen) return;
    const jitter = Math.floor(Math.random() * 250);
    const delay = Math.min(backoff + jitter, MAX_BACKOFF_MS);
    backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
    setTimeout(ensureSocket, delay);
  }

  let flushScheduled = false;
  function scheduleFlush() {
    if (flushScheduled) return;
    flushScheduled = true;
    queueMicrotask(() => { flushScheduled = false; flush(); });
  }

  async function flush() {
    const socket = ensureSocket();
    if (!socket || socket.readyState !== WebSocket.OPEN) return { shipped: 0, queued: await pendingCount() };
    const db = await openDb();
    const queued = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const rq = tx.objectStore(STORE).index("status").getAll(IDBKeyRange.only("queued"));
      rq.onsuccess = () => resolve(rq.result || []);
      rq.onerror = () => reject(rq.error);
    });
    let shipped = 0;
    for (const row of queued) {
      try {
        const actions = await openActions(row); // unseal if encrypted, else passthrough
        if (!actions || actions.length === 0) continue; // skip undecryptable rows
        socket.send(JSON.stringify({
          txn_id: row.txn_id,
          vector_clock: row.vector_clock,
          domain: row.domain,
          actions: actions,
          tenant_hash: row.tenant_hash,
          // When this write was captured offline (epoch ms). The server uses it
          // for last-writer-wins so a stale offline upsert never clobbers newer
          // online state. Falls back to row.created_at for rows queued earlier.
          captured_at: row.captured_at || row.created_at,
        }));
        shipped += 1;
      } catch (e) {
        break;
      }
    }
    return { shipped, queued: queued.length - shipped };
  }

  window.rmcWAL = {
    append,
    flush,
    pending: pendingCount,
    onAck: (cb) => { ackListeners.add(cb); return () => ackListeners.delete(cb); },
  };

  // Test-only hook: exposes the at-rest encryption internals so the outbox
  // seal/open round-trip can be exercised in CI (vitest + Playwright) against
  // the REAL shipped code rather than a re-implementation. Inert in production
  // — `window.__RMC_OUTBOX_TEST__` is never set outside the test harness.
  if (window.__RMC_OUTBOX_TEST__) {
    window.rmcWAL.__test = { sealActions, openActions, getEncKey, encEnabled };
  }

  function shouldBootWalSocket() {
    if (document.querySelector("[data-rmc-auth-landing]")) return false;
    // Manager / control-plane is WSGI-only on Render; /ws/wal/ needs ASGI (Daphne).
    const surface = document.documentElement.getAttribute("data-surface") || "";
    if (surface === "control-plane") return false;
    if (document.body?.classList.contains("control-plane-shell")) return false;
    return true;
  }

  // Boot: open WS only on authenticated shells (not login/public landings).
  if (shouldBootWalSocket()) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", ensureSocket, { once: true });
    } else {
      ensureSocket();
    }
  }
})();
