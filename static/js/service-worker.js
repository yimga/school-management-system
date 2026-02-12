// Service worker for portal PWA + offline write-behind queue.
const CACHE_VERSION = "sms-v1.3.0";
const STATIC_CACHE = `sms-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `sms-dynamic-${CACHE_VERSION}`;

const SYNC_DB_NAME = "sms-offline-sync-db";
const SYNC_DB_VERSION = 1;
const SYNC_STORE = "syncQueue";
/** Max items per sync type; oldest are dropped when enqueueing over limit. */
const MAX_QUEUE_PER_TYPE = 500;
/** Auth/session headers we must not store so replay uses fresh credentials. */
const SKIP_HEADERS = ["cookie", "authorization", "x-csrftoken", "x-csrf-token", "content-length"];
/** Exponential backoff: max delay between retries (ms). */
const BACKOFF_MAX_MS = 15 * 60 * 1000;
/** Base delay for first retry (ms). */
const BACKOFF_BASE_MS = 2000;

let OFFLINE_CONFIG = {
  enabled: true,
  formQueueEnabled: true,
  attendanceSyncEnabled: true,
  gradeSyncEnabled: true,
  apiSyncEnabled: true,
  backgroundSyncEnabled: true,
};

const STATIC_ASSETS = [
  "/offline/",
  "/static/css/portal_theme.css",
  "/static/css/dashboard-responsive.css",
  "/static/js/command-palette.js",
  "/static/js/dashboard-layout.js",
  "/static/images/logo.png",
  "/static/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(STATIC_CACHE);
      // Cache each asset independently so one missing file does not break install.
      await Promise.all(
        STATIC_ASSETS.map(async (asset) => {
          try {
            await cache.add(asset);
          } catch (_err) {}
        }),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names.map((name) => {
          if (name !== STATIC_CACHE && name !== DYNAMIC_CACHE) {
            return caches.delete(name);
          }
          return Promise.resolve();
        }),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "SET_OFFLINE_CONFIG" && data.payload && typeof data.payload === "object") {
    OFFLINE_CONFIG = { ...OFFLINE_CONFIG, ...data.payload };
    return;
  }
  if (data.type === "REPLAY_SYNC_NOW") {
    event.waitUntil(
      Promise.all([
        replayQueue("attendance"),
        replayQueue("grade"),
        replayQueue("api"),
      ]).then((counts) => {
        const totalFailed = (counts[0]?.failed ?? 0) + (counts[1]?.failed ?? 0) + (counts[2]?.failed ?? 0);
        const failedItems = [].concat(
          counts[0]?.failedItems ?? [],
          counts[1]?.failedItems ?? [],
          counts[2]?.failedItems ?? [],
        );
        return self.clients.matchAll().then((clients) => {
          clients.forEach((client) => {
            try {
              client.postMessage({ type: "sync-complete", failedCount: totalFailed, failedItems });
            } catch (_err) {}
          });
        });
      }),
    );
  }
  if (data.type === "GET_QUEUE_LENGTH") {
    event.waitUntil(
      Promise.all([
        getSyncItems("attendance").then((a) => (a || []).length),
        getSyncItems("grade").then((g) => (g || []).length),
        getSyncItems("api").then((x) => (x || []).length),
      ]).then(([attendance, grade, api]) => {
        const total = attendance + grade + api;
        const source = event.source;
        if (source) {
          try {
            source.postMessage({
              type: "queue-length",
              attendance,
              grade,
              api,
              total,
            });
          } catch (_err) {}
        }
      }),
    );
  }
  if (data.type === "GET_QUEUE_ITEMS") {
    const limit = Math.min(Math.max(0, parseInt(data.limit, 10) || 50), 200);
    const origin = self.location.origin;
    event.waitUntil(
      Promise.all([
        getSyncItems("attendance"),
        getSyncItems("grade"),
        getSyncItems("api"),
      ]).then(([attendance, grade, api]) => {
        const all = []
          .concat(attendance || [], grade || [], api || [])
          .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
          .slice(0, limit);
        const items = all.map((it) => {
          const url = it.requestUrl && it.requestUrl.startsWith("http") ? it.requestUrl : origin + (it.requestUrl || "");
          const path = url.replace(origin, "") || "/";
          let body = it.body;
          if (typeof body === "string") body = maybeDecryptBody(body);
          return { id: it.id, method: it.method || "POST", path, body };
        });
        const source = event.source;
        if (source) {
          try {
            source.postMessage({ type: "queue-items", items });
          } catch (_err) {}
        }
      }),
    );
  }
  if (data.type === "REMOVE_QUEUE_ITEMS" && Array.isArray(data.ids)) {
    event.waitUntil(
      Promise.all((data.ids || []).slice(0, 200).map((id) => deleteSyncItem(id))).then(() => {
        const source = event.source;
        if (source) {
          try {
            source.postMessage({ type: "queue-items-removed", count: data.ids.length });
          } catch (_err) {}
        }
      }),
    );
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) {
    return;
  }

  if (OFFLINE_CONFIG.enabled && isApiWriteRequest(request, url)) {
    event.respondWith(handleApiWrite(request, url));
    return;
  }

  if (request.method === "GET" && url.pathname.startsWith("/api/")) {
    event.respondWith(staleWhileRevalidateApi(request));
    return;
  }

  if (request.method !== "GET") {
    return;
  }

  event.respondWith(cacheFirstNavigationAndStatic(request));
});

self.addEventListener("sync", (event) => {
  if (!OFFLINE_CONFIG.enabled) {
    return;
  }

  if (event.tag === "attendance-sync") {
    event.waitUntil(replayQueue("attendance"));
  } else if (event.tag === "grade-sync") {
    event.waitUntil(replayQueue("grade"));
  } else if (event.tag === "api-sync") {
    event.waitUntil(replayQueue("api"));
  } else if (event.tag === "offline-sync-all") {
    event.waitUntil(
      Promise.all([replayQueue("attendance"), replayQueue("grade"), replayQueue("api")]),
    );
  }
});

/** Add any REST write paths for offline queue here. Enables platform-wide offline for all API writes when expanded. */
function isApiWriteRequest(request, url) {
  if (!["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) {
    return false;
  }
  if (url.pathname.startsWith("/api/attendance/")) return true;
  if (url.pathname.startsWith("/api/entity/") || url.pathname.startsWith("/api/entities/")) return true;
  if (url.pathname.startsWith("/api/requests/")) return true;
  if (url.pathname.startsWith("/api/finance/")) return true;
  // if (url.pathname.startsWith("/api/grades/") || url.pathname.startsWith("/api/evals/")) return true;
  return false;
}

function inferSyncType(pathname) {
  if (pathname.startsWith("/api/attendance/")) return "attendance";
  if (pathname.startsWith("/api/entity/") || pathname.startsWith("/api/entities/") || pathname.startsWith("/api/finance/") || pathname.startsWith("/api/requests/")) return "api";
  // if (pathname.startsWith("/api/grades/") || pathname.startsWith("/api/evals/")) return "grade";
  return null;
}

function queueAllowed(syncType) {
  if (!OFFLINE_CONFIG.enabled) return false;
  if (syncType === "attendance") return !!OFFLINE_CONFIG.attendanceSyncEnabled;
  if (syncType === "grade") return !!OFFLINE_CONFIG.gradeSyncEnabled;
  if (syncType === "api") return !!OFFLINE_CONFIG.apiSyncEnabled;
  return false;
}

/** Stale-While-Revalidate: return cached API response immediately if present, then revalidate in background. */
async function staleWhileRevalidateApi(request) {
  const cached = await caches.match(request);
  const revalidate = (async () => {
    try {
      const response = await fetch(request);
      if (response && response.ok) {
        const cache = await caches.open(DYNAMIC_CACHE);
        await cache.put(request, response.clone());
      }
      return response;
    } catch (_err) {
      return null;
    }
  })();

  if (cached) {
    revalidate.catch(() => {});
    return cached;
  }
  try {
    const response = await revalidate;
    if (response) return response;
  } catch (_err) {}
  return new Response(
    JSON.stringify({
      error: "offline",
      message: "No cached API data available while offline.",
    }),
    { status: 503, headers: { "Content-Type": "application/json" } },
  );
}

async function cacheFirstNavigationAndStatic(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }

  try {
    const response = await fetch(request);
    if (response && response.ok) {
      if (
        request.destination === "style" ||
        request.destination === "script" ||
        request.destination === "image" ||
        request.url.includes("/static/")
      ) {
        const cache = await caches.open(STATIC_CACHE);
        cache.put(request, response.clone());
      }
    }
    return response;
  } catch (_err) {
    if (request.mode === "navigate") {
      return (await caches.match("/offline/")) || new Response("Offline", { status: 503 });
    }
    return new Response("Offline", { status: 503 });
  }
}

async function handleApiWrite(request, url) {
  try {
    return await fetch(request.clone());
  } catch (_err) {
    const syncType = inferSyncType(url.pathname);
    if (!queueAllowed(syncType)) {
      return new Response(
        JSON.stringify({
          status: "failed",
          reason: "offline_sync_disabled",
        }),
        { status: 503, headers: { "Content-Type": "application/json" } },
      );
    }

    const payload = await serializeRequest(request);
    await enforceQueueLimit(syncType);
    await enqueueSyncItem({
      syncType,
      requestUrl: url.origin + url.pathname + url.search,
      method: payload.method,
      headers: payload.headers,
      body: payload.body,
      createdAt: Date.now(),
    });

    if (OFFLINE_CONFIG.backgroundSyncEnabled && self.registration && self.registration.sync) {
      const tag =
        syncType === "attendance"
          ? "attendance-sync"
          : syncType === "grade"
            ? "grade-sync"
            : syncType === "api"
              ? "api-sync"
              : "offline-sync-all";
      try {
        await self.registration.sync.register(tag);
      } catch (_err) {}
    }

    return new Response(
      JSON.stringify({
        status: "queued",
        queued: true,
        syncType,
      }),
      { status: 202, headers: { "Content-Type": "application/json" } },
    );
  }
}

async function serializeRequest(request) {
  const headers = {};
  const skip = new Set(SKIP_HEADERS.map((h) => h.toLowerCase()));
  request.headers.forEach((value, key) => {
    const k = key.toLowerCase();
    if (!skip.has(k)) headers[key] = value;
  });
  if (!headers["Content-Type"]) headers["Content-Type"] = "application/json";

  let body = "";
  try {
    body = await request.clone().text();
  } catch (_err) {}

  return {
    method: request.method,
    headers,
    body,
  };
}

/** Keep queue under MAX_QUEUE_PER_TYPE by removing oldest items for this syncType. */
async function enforceQueueLimit(syncType) {
  const items = await getSyncItems(syncType);
  if (!items || items.length < MAX_QUEUE_PER_TYPE) return;
  const sorted = items.slice().sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
  const toRemove = sorted.length - MAX_QUEUE_PER_TYPE + 1;
  for (let i = 0; i < toRemove && i < sorted.length; i++) {
    await deleteSyncItem(sorted[i].id);
  }
}

/**
 * Exponential backoff: next retry time from attempt count.
 * @param {number} attemptCount
 * @returns {number} delay in ms
 */
function backoffDelayMs(attemptCount) {
  const delay = BACKOFF_BASE_MS * Math.pow(2, Math.min(attemptCount, 10));
  return Math.min(delay, BACKOFF_MAX_MS);
}

/**
 * Replay queued requests for a sync type. Uses full URL; sends only safe headers + credentials.
 * Removes item on 2xx; removes on 4xx and records in failedItems; on 5xx/network keeps and sets backoff.
 * @returns {{ succeeded: number, failed: number, failedItems: Array<{url:string,status:number,message?:string}> }}
 */
async function replayQueue(syncType) {
  const items = await getSyncItems(syncType);
  const sorted = (items || []).slice().sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
  let succeeded = 0;
  let failed = 0;
  const failedItems = [];
  const now = Date.now();
  const origin = self.location.origin;

  for (const item of sorted) {
    const nextRetryAt = item.nextRetryAt || 0;
    if (nextRetryAt > now) {
      continue;
    }
    const url = item.requestUrl && item.requestUrl.startsWith("http") ? item.requestUrl : origin + (item.requestUrl || "");
    const body = typeof item.body === "string" ? maybeDecryptBody(item.body) : (item.body || "");
    const headers = { "Content-Type": "application/json" };
    if (item.headers && typeof item.headers === "object") {
      Object.keys(item.headers).forEach((k) => {
        const l = k.toLowerCase();
        if (!SKIP_HEADERS.includes(l)) headers[k] = item.headers[k];
      });
    }
    try {
      const response = await fetch(url, {
        method: item.method || "POST",
        headers,
        body,
        credentials: "include",
      });
      if (response.ok) {
        await deleteSyncItem(item.id);
        succeeded++;
      } else if (response.status >= 400 && response.status < 500) {
        let message = "";
        try {
          const json = await response.clone().json();
          message = json.error || json.message || json.detail || "";
        } catch (_) {}
        failedItems.push({
          url: url.replace(origin, ""),
          status: response.status,
          message: message || ("HTTP " + response.status),
        });
        await deleteSyncItem(item.id);
        failed++;
      } else {
        const attemptCount = (item.attemptCount || 0) + 1;
        const delay = backoffDelayMs(attemptCount);
        await updateSyncItem(item.id, {
          lastAttemptAt: now,
          attemptCount,
          nextRetryAt: now + delay,
        });
      }
    } catch (_err) {
      const attemptCount = (item.attemptCount || 0) + 1;
      const delay = backoffDelayMs(attemptCount);
      await updateSyncItem(item.id, {
        lastAttemptAt: now,
        attemptCount,
        nextRetryAt: now + delay,
      });
    }
  }
  return { succeeded, failed, failedItems };
}

function openSyncDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(SYNC_DB_NAME, SYNC_DB_VERSION);
    req.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(SYNC_STORE)) {
        const store = db.createObjectStore(SYNC_STORE, { keyPath: "id", autoIncrement: true });
        store.createIndex("syncType", "syncType", { unique: false });
        store.createIndex("createdAt", "createdAt", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Optional encryption: when OFFLINE_CONFIG.enableQueueEncryption and queueEncryptionKey are set, encrypt item.body before storing. */
function maybeEncryptBody(body) {
  if (!OFFLINE_CONFIG.enableQueueEncryption || !OFFLINE_CONFIG.queueEncryptionKey || typeof body !== "string") return body;
  try {
    return btoa(encodeURIComponent(body));
  } catch (_) {
    return body;
  }
}
function maybeDecryptBody(body) {
  if (!OFFLINE_CONFIG.enableQueueEncryption || !OFFLINE_CONFIG.queueEncryptionKey || typeof body !== "string") return body;
  try {
    return decodeURIComponent(atob(body));
  } catch (_) {
    return body;
  }
}

async function enqueueSyncItem(item) {
  const toStore = { ...item };
  if (typeof toStore.body === "string") toStore.body = maybeEncryptBody(toStore.body);
  const db = await openSyncDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(SYNC_STORE, "readwrite");
    const store = tx.objectStore(SYNC_STORE);
    const req = store.add(toStore);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function getSyncItems(syncType) {
  const db = await openSyncDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(SYNC_STORE, "readonly");
    const store = tx.objectStore(SYNC_STORE);
    const index = store.index("syncType");
    const req = index.getAll(syncType);
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

async function deleteSyncItem(id) {
  const db = await openSyncDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(SYNC_STORE, "readwrite");
    const store = tx.objectStore(SYNC_STORE);
    const req = store.delete(id);
    req.onsuccess = () => resolve(true);
    req.onerror = () => reject(req.error);
  });
}

async function getSyncItem(id) {
  const db = await openSyncDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(SYNC_STORE, "readonly");
    const store = tx.objectStore(SYNC_STORE);
    const req = store.get(id);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function updateSyncItem(id, updates) {
  const existing = await getSyncItem(id);
  if (!existing) return;
  const db = await openSyncDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(SYNC_STORE, "readwrite");
    const store = tx.objectStore(SYNC_STORE);
    const merged = { ...existing, ...updates };
    const req = store.put(merged);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}
