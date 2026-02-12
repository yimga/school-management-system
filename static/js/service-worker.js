// Service worker for portal PWA + offline write-behind queue.
const CACHE_VERSION = "sms-v1.2.0";
const STATIC_CACHE = `sms-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `sms-dynamic-${CACHE_VERSION}`;

const SYNC_DB_NAME = "sms-offline-sync-db";
const SYNC_DB_VERSION = 1;
const SYNC_STORE = "syncQueue";

let OFFLINE_CONFIG = {
  enabled: true,
  formQueueEnabled: true,
  attendanceSyncEnabled: true,
  gradeSyncEnabled: true,
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
  } else if (event.tag === "offline-sync-all") {
    event.waitUntil(Promise.all([replayQueue("attendance"), replayQueue("grade")]));
  }
});

/** Add any REST write paths for offline queue here. Grade writes currently use form queue (form-draft-save) + sync when online. */
function isApiWriteRequest(request, url) {
  if (!["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) {
    return false;
  }
  if (url.pathname.startsWith("/api/attendance/")) return true;
  // if (url.pathname.startsWith("/api/grades/") || url.pathname.startsWith("/api/evals/")) return true;
  return false;
}

function inferSyncType(pathname) {
  if (pathname.startsWith("/api/attendance/")) return "attendance";
  // if (pathname.startsWith("/api/grades/") || pathname.startsWith("/api/evals/")) return "grade";
  return null;
}

function queueAllowed(syncType) {
  if (!OFFLINE_CONFIG.enabled) return false;
  if (syncType === "attendance") return !!OFFLINE_CONFIG.attendanceSyncEnabled;
  if (syncType === "grade") return !!OFFLINE_CONFIG.gradeSyncEnabled;
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
    await enqueueSyncItem({
      syncType,
      requestUrl: url.pathname + url.search,
      method: payload.method,
      headers: payload.headers,
      body: payload.body,
      createdAt: Date.now(),
    });

    if (OFFLINE_CONFIG.backgroundSyncEnabled && self.registration && self.registration.sync) {
      const tag = syncType === "attendance" ? "attendance-sync" : "grade-sync";
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
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "content-length") {
      headers[key] = value;
    }
  });

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

async function replayQueue(syncType) {
  const items = await getSyncItems(syncType);
  for (const item of items) {
    try {
      const body = typeof item.body === "string" ? maybeDecryptBody(item.body) : (item.body || "");
      const response = await fetch(item.requestUrl, {
        method: item.method || "POST",
        headers: item.headers || { "Content-Type": "application/json" },
        body: body,
        credentials: "include",
      });
      if (response && response.ok) {
        await deleteSyncItem(item.id);
      }
    } catch (_err) {
      // Keep item in queue for next retry.
    }
  }
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
