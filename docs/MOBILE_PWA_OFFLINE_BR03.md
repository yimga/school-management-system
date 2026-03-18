# Mobile / PWA / offline (BR-03)

## Done in product

- **`static/manifest-portal.json`:** Parent portal PWA install (name, icons placeholder, `start_url` `/portal/parent/`).
- **Portal parent base:** `<link rel="manifest">` on parent paths.
- **Service worker:** When `enable_portal_pwa` is on, parent portal (`/portal/parent/`, `/parent/dashboard`) registers `static/js/service-worker.js` even if tenant-wide offline mode is off — **shell + shared queue infrastructure** (same worker as teacher/staff when full offline is enabled).
- **Full offline bar + Dexie scripts:** Still require `enable_offline_mode` + `SHOW_OFFLINE_STATUS_BAR` (see `context_processors`).

## Runbook (phase 2)

1. Register service worker on `/portal/static/sw-portal.js` (cache shell + parent_dashboard).
2. Queue POST actions in IndexedDB; replay on `online` event.
3. QA: airplane mode on parent dashboard.

## QA sign-off checklist

- [ ] Install PWA from Chrome (Android) on parent URL
- [ ] Parent dashboard loads after install
- [ ] (Phase 2) Offline banner + sync
