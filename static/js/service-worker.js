// Service worker for portal PWA + offline write-behind queue.
// Bumped 2026-05-13 (v2.6.0): Shell polish + breadth adoption.
//   - Progress bar, OG/Twitter meta, safe-area mobile guards, keyboard
//     cheat sheet, marketing dark-mode tokens, and native form-validation
//     feedback are mounted across the shell family.
//   - Empty-state, metric ticker, and bento grid breadth extended across
//     high-traffic dashboards plus pricing/platform/admin hubs.
// Bumped 2026-05-12 (v2.5.0): Carried-forward closeout — completes the 4
// follow-ups from v2.4 aesthetic push as a single wave.
//   - SITE_LOGO_DARK_URL: RuntimeDefaults typed column (migration 0065) +
//     SiteSettings dispatch + context-processor cascade with tenant override
//     via BrandProfile.logo_dark_url + meta-tag bridge + theme bootstrap
//     propagation as --site-logo-url/--site-logo-dark-url CSS variables +
//     .rmc-logo-adaptive background-image swap rule + <img> swap in
//     rmc-shell-polish.js. The dark favicon variant shipped in v2.4; now
//     the in-page logo completes the dark-mode brand cascade.
//   - View Transitions API: @view-transition { navigation: auto } + named
//     persistent regions (rmc-topbar, rmc-main) so cross-doc navigation
//     glides instead of flashes on Chromium 126+. Other browsers fall back
//     to native instant nav. prefers-reduced-motion fully honored.
//   - Bento grid component (templates/marketing/partials/mkt_bento.html +
//     .mkt-bento grammar in marketing-landing-v2.css): mixed-tile composition
//     for marketing landing with 5 size spans (sm/md/lg/wide/tall) + 4 tones
//     (default/warm/sand/ink) + reduced-motion-aware hover. Adopted on
//     /v2 between the ROI panel and the globe section; data lives in the
//     view (configurability + i18n).
//   - Sticky metric ticker (.rmc-metric-ticker + rmc-metric-ticker.js):
//     Apple Stocks-style pinned KPI strip — when the user scrolls past
//     the full KPI block, a condensed mirror pins below the topbar via
//     IntersectionObserver. Adopted on the school command center stats
//     core strip; mount script loaded on all 4 surface shells.
// Bumped 2026-05-12 (v2.0.0): Class-tier polish wave (Phases J–W).
//   - Palette refinement: single-accent luminous gradient + warm-graphite opt-in
//     (data-rmc-neutral) + Apple HIG status hues + tenant-cascade variables
//     (--brand-gradient-end / --brand-gradient-angle).
//   - .rmc-data-table grammar (hairline grid, tabular nums, zebra 2%, sticky header,
//     density toggle) bridged onto existing .gradebook-table so 6 templates upgrade
//     without per-template edits.
//   - Empty-state + skeleton primitives (rmc_empty_state.html / rmc_skeleton.html /
//     .rmc-empty / .rmc-skeleton with 5 shapes).
//   - Motion vocabulary: --motion-fast/normal/slow/spring/decel + .rmc-anim-rise/
//     slide-in/fade/spring, reduced-motion fully honored.
//   - Avatar / identity system: rmc_avatar.html + deterministic 10-palette gradient
//     seeded by user pk, status ring (active/away/offline), stacked avatars.
//   - Notifications inbox rewritten (grouped by severity, indicator stripe for
//     unread, avatar + actions inline) and toast grammar (frosted + slide-from-top
//     with overshoot + progress bar + max stack).
//   - Forms grammar (.rmc-form-section/.rmc-form-field/.rmc-form-savebar) + dirty-
//     state JS + beforeunload guard.
//   - Print stylesheet (rmc-print.css) for report cards / transcripts / invoices.
//   - Settings IA hub at /portal/configure/ (Apple Settings-app left rail + search
//     + 8 categories: Brand / Academics / Finance / People / Notifications / AI /
//     Integrations / Compliance).
//   - Chart aesthetic refresh (hairline grid, single-accent series, frosted
//     tooltip, sparkline grammar, KPI-with-trend block).
//   - Spring success checkmark + haptic helper (Navigator.vibrate on
//     rmc:success/warning/error events, reduced-motion-respecting).
//   - 834px iPad split-view breakpoint adopted across components.
const CACHE_VERSION = "sms-v2.44.0-warm-bright-non-shell-sweep-2026-05-15";
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

// Pass 11.B: forward SW errors to controlled clients so the in-page Sentry
// bridge (static/js/sentry-browser-bridge.js) can POST them to the observability
// endpoint. Wrapped in a try/catch because clients.matchAll() rejects when there
// are no controlled clients yet (very early SW startup).
function _broadcastSwError(payload) {
  try {
    self.clients.matchAll({ includeUncontrolled: false, type: "window" }).then(function (clients) {
      clients.forEach(function (client) {
        try {
          client.postMessage(Object.assign({ type: "sw-error" }, payload));
        } catch (_) { /* one bad client must not block the rest */ }
      });
    }).catch(function () { /* no clients = no-op */ });
  } catch (_) { /* defensive: never crash on telemetry */ }
}

self.addEventListener("error", function (event) {
  _broadcastSwError({
    level: "error",
    message: String((event && (event.message || (event.error && event.error.message))) || "SW error"),
    url: String((event && event.filename) || ""),
    stack: String((event && event.error && event.error.stack) || "")
  });
});

self.addEventListener("unhandledrejection", function (event) {
  var reason = (event && event.reason) || {};
  _broadcastSwError({
    level: "error",
    message: String(reason.message || reason || "SW unhandled rejection"),
    url: "",
    stack: String(reason.stack || "")
  });
});

let OFFLINE_CONFIG = {
  enabled: true,
  formQueueEnabled: true,
  attendanceSyncEnabled: true,
  gradeSyncEnabled: true,
  apiSyncEnabled: true,
  /** Explicit toggle for sync_batch (attendance + grades + offline_payment replay). */
  paymentSyncEnabled: true,
  entitySyncEnabled: true,
  requestsSyncEnabled: true,
  backgroundSyncEnabled: true,
  hubBaseUrl: "",
};

// Cache manifest — WhiteNoise (CompressedManifestStaticFilesStorage) serves both
// hashed and unhashed paths, so /static/css/foo.css resolves whether collectstatic
// produced foo.HASH.css or foo.css. To make this truly path-independent (CDN
// migration, STATIC_URL change), serve service-worker.js via a Django-rendered
// view that injects {% static %} tags. Tracked in reference_configurability_contract.md.
// portal_theme.css removed 2026-05-10: retired, conflicts with token system.
const STATIC_ASSETS = [
  "/offline/",
  "/static/css/design-tokens.css",
  "/static/css/rmc-class-grammar.css",
  "/static/css/rmc-warm-bright-school.css",
  "/static/css/dashboard-responsive.css",
  "/static/css/reduce-motion-low-power.css",
  // command-palette.js retired 2026-05-12 — replaced by rmc-command-palette.js
  // (which is loaded per-page from the rmc_command_palette.html include, so it
  // doesn't need to be in the offline pre-cache).
  "/static/js/dashboard-layout.js",
  "/static/js/vendor/dexie.min.js",
  "/static/js/offline-db.js",
  "/static/js/form-draft-save.js",
  "/static/js/sync-manager.js",
  "/static/js/low-power.js",
  "/static/js/offline-status-bar.js",
  "/static/js/auto-pilot.js",
  "/static/js/migration_cloud_wizard.js",
  "/static/images/logo.png",
  "/static/manifest.json",
];

// Resolve pre-cache asset list at install time. Tries /sw-asset-manifest.json
// (Django view that emits `{% static %}`-resolved URLs respecting STATIC_URL +
// WhiteNoise content hashes); falls back to the hardcoded STATIC_ASSETS array
// if the endpoint is unreachable (e.g. fresh install offline).
async function _resolveAssetList() {
  try {
    const resp = await fetch("/sw-asset-manifest.json", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (resp.ok) {
      const data = await resp.json();
      if (data && Array.isArray(data.assets) && data.assets.length) {
        return data.assets;
      }
    }
  } catch (_err) {}
  return STATIC_ASSETS;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(STATIC_CACHE);
      const assets = await _resolveAssetList();
      // Cache each asset independently so one missing file does not break install.
      await Promise.all(
        assets.map(async (asset) => {
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
  if (data.type === "SKIP_WAITING") {
    // Page asked us to take over immediately. Pair with the registration
    // script's controllerchange → reload handler so the new SW + new HTML
    // reach the user without a manual hard-refresh.
    self.skipWaiting();
    return;
  }
  if (data.type === "REPLAY_SYNC_NOW") {
    event.waitUntil(
      (async () => {
        const counts = [];
        counts.push(await replayQueue("attendance"));
        counts.push(await replayQueue("grade"));
        counts.push(await replayQueue("api"));
        const totalFailed = (counts[0]?.failed ?? 0) + (counts[1]?.failed ?? 0) + (counts[2]?.failed ?? 0);
        const failedItems = [].concat(
          counts[0]?.failedItems ?? [],
          counts[1]?.failedItems ?? [],
          counts[2]?.failedItems ?? [],
        );
        const clients = await self.clients.matchAll();
        clients.forEach((client) => {
          try {
            client.postMessage({ type: "sync-complete", failedCount: totalFailed, failedItems });
          } catch (_err) {}
        });
      })(),
    );
  }
  if (data.type === "REPLAY_SYNC_BATCH") {
    const limit = Math.min(Math.max(1, parseInt(data.limit, 10) || 10), 50);
    event.waitUntil(
      (async () => {
        const counts = [];
        counts.push(await replayQueueLimit("attendance", limit));
        counts.push(await replayQueueLimit("grade", limit));
        counts.push(await replayQueueLimit("api", limit));
        const totalFailed = (counts[0]?.failed ?? 0) + (counts[1]?.failed ?? 0) + (counts[2]?.failed ?? 0);
        const failedItems = [].concat(
          counts[0]?.failedItems ?? [],
          counts[1]?.failedItems ?? [],
          counts[2]?.failedItems ?? [],
        );
        const clients = await self.clients.matchAll();
        clients.forEach((client) => {
          try {
            client.postMessage({ type: "sync-complete", failedCount: totalFailed, failedItems, batch: true });
          } catch (_err) {}
        });
      })(),
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
    const limit = Math.min(Math.max(0, parseInt(data.limit, 10) || 50), 500);
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

  if (OFFLINE_CONFIG.enabled && isApiWriteRequest(request, url) && isApiWriteAllowedByToggles(url)) {
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
      (async () => {
        await replayQueue("attendance");
        await replayQueue("grade");
        await replayQueue("api");
      })(),
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
  /** Unified offline replay: attendance, grades, offline_payment intents (POST sync_batch). */
  if (url.pathname.startsWith("/api/sync/")) return true;
  // Offline foundational (2026-05-11): teacher grade entry now queues offline.
  if (url.pathname.startsWith("/api/grades/") || url.pathname.startsWith("/api/evals/")) return true;
  return false;
}

function inferSyncType(pathname) {
  if (pathname.startsWith("/api/attendance/")) return "attendance";
  if (pathname.startsWith("/api/entity/") || pathname.startsWith("/api/entities/") || pathname.startsWith("/api/finance/") || pathname.startsWith("/api/requests/")) return "api";
  if (pathname.startsWith("/api/grades/") || pathname.startsWith("/api/evals/")) return "grade";
  return null;
}

function queueAllowed(syncType) {
  if (!OFFLINE_CONFIG.enabled) return false;
  if (syncType === "attendance") return !!OFFLINE_CONFIG.attendanceSyncEnabled;
  if (syncType === "grade") return !!OFFLINE_CONFIG.gradeSyncEnabled;
  if (syncType === "api") {
    return !!(
      OFFLINE_CONFIG.apiSyncEnabled ||
      OFFLINE_CONFIG.entitySyncEnabled ||
      OFFLINE_CONFIG.requestsSyncEnabled ||
      OFFLINE_CONFIG.paymentSyncEnabled
    );
  }
  return false;
}

function isApiWriteAllowedByToggles(url) {
  const path = url.pathname || "";
  if (path.startsWith("/api/sync/")) {
    return !!(
      OFFLINE_CONFIG.attendanceSyncEnabled ||
      OFFLINE_CONFIG.gradeSyncEnabled ||
      OFFLINE_CONFIG.apiSyncEnabled ||
      OFFLINE_CONFIG.paymentSyncEnabled
    );
  }
  if (path.startsWith("/api/entity") || path.startsWith("/api/entities")) return !!OFFLINE_CONFIG.entitySyncEnabled;
  if (path.startsWith("/api/requests/")) return !!OFFLINE_CONFIG.requestsSyncEnabled;
  if (path.startsWith("/api/finance/")) return !!OFFLINE_CONFIG.apiSyncEnabled;
  return !!OFFLINE_CONFIG.apiSyncEnabled;
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
    const hubBaseUrl = (OFFLINE_CONFIG.hubBaseUrl || "").trim();
    if (hubBaseUrl) {
      const hubOrigin = hubBaseUrl.replace(/\/$/, "");
      const hubUrl = hubOrigin + url.pathname + url.search;
      try {
        const body = await request.clone().text();
        const headers = {};
        request.headers.forEach((value, key) => {
          const k = key.toLowerCase();
          if (!["cookie", "authorization", "content-length"].includes(k)) headers[key] = value;
        });
        if (!headers["Content-Type"]) headers["Content-Type"] = "application/json";
        const res = await fetch(hubUrl, {
          method: request.method,
          headers,
          body: body || undefined,
          credentials: "omit",
        });
        if (res.ok) return res;
      } catch (_hubErr) {}
    }
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
async function fetchFreshCsrfToken(origin) {
  /** Offline foundational: pull a fresh X-CSRFToken before replaying.
   *  The csrftoken cookie may have rotated while POSTs were queued. */
  try {
    const res = await fetch(origin + "/api/csrf-token/", {
      method: "GET",
      credentials: "include",
      headers: { "Accept": "application/json" },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data && data.csrf_token ? data.csrf_token : null;
  } catch (_err) {
    return null;
  }
}

async function replayQueue(syncType) {
  const items = await getSyncItems(syncType);
  const sorted = (items || []).slice().sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
  let succeeded = 0;
  let failed = 0;
  const failedItems = [];
  const now = Date.now();
  const origin = self.location.origin;

  // Refresh CSRF token once per replay batch — pulls a fresh value if the
  // cookie has rotated since the queued POSTs were captured.
  const freshCsrf = sorted.length ? await fetchFreshCsrfToken(origin) : null;

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
    if (freshCsrf) {
      headers["X-CSRFToken"] = freshCsrf;
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

/**
 * Replay up to `limit` items for a sync type (for drip/batch replay).
 * @param {string} syncType
 * @param {number} limit
 * @returns {{ succeeded: number, failed: number, failedItems: Array }}
 */
async function replayQueueLimit(syncType, limit) {
  const items = await getSyncItems(syncType);
  const sorted = (items || []).slice().sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
  const now = Date.now();
  const toReplay = [];
  for (const item of sorted) {
    if (toReplay.length >= limit) break;
    if ((item.nextRetryAt || 0) <= now) toReplay.push(item);
  }
  let succeeded = 0;
  let failed = 0;
  const failedItems = [];
  const origin = self.location.origin;
  for (const item of toReplay) {
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
