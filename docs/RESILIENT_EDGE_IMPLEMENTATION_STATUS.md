# Resilient Edge – Implementation Status

This document tracks completion of the Resilient Edge plan and related OFFLINE_MODE_* docs. **Phase 2 and all optional/suggested items from the plan are included.**

**Sign-off:** See [RESILIENT_EDGE_COMPLETION_CHECKLIST.md](RESILIENT_EDGE_COMPLETION_CHECKLIST.md) for a one-page verification checklist.

---

## Completed – Core (Section 5 and Section 3)

| # | Item | Notes |
|---|------|--------|
| 1 | **Replay priority** | SW replays **sequentially**: attendance → grade → api. `static/js/service-worker.js`. |
| 2 | **Client schema + mirror** | `static/js/offline-db.js` (Dexie): students, attendance, evaluations, classrooms, **ocr_corrections**. Hydrate on load and after sync. |
| 3 | **Sync manager** | `static/js/sync-manager.js`: Sync now, hydrateAfterSync, getDripMode, **requestSyncBatch**, **sendDeltaBatch**. |
| 4 | **reachabilityUrl** | `SMS_OFFLINE_CONFIG.reachabilityUrl`; default `/health/` or `SITE.backend_feature_flags.reachability_url`. |
| 5 | **Drip when weak** | No auto-replay on `online` when getDripMode(); only manual “Sync now”. When drip on, “Sync now” uses **REPLAY_SYNC_BATCH** (limit 10). |
| 6 | **Low power / Save Data** | Backend flag `reduce_activity_low_power`; `low-power.js` + `reduce-motion-low-power.css`. |
| 7 | **Offline page copy** | `templates/offline.html`: “When back online … use **Sync now** in the header.” |
| 8 | **PWA precache** | STATIC_ASSETS includes Dexie, offline-db, sync-manager, low-power, offline-status-bar, **auto-pilot**, reduce-motion-low-power.css. |
| 9 | **E2E tests** | `tests/e2e/offline-sync.spec.js`: offline fallback, offline→online recovery, **authenticated** (login, offline, online, Sync now) when TEST_USERNAME/TEST_PASSWORD set. |

---

## Completed – Phase 2 and Optionals

| Item | Status | Notes |
|------|--------|-------|
| **Delta endpoint (server)** | Done | `apps/api/sync_delta_api.py`: POST `/api/offline/delta/` with `items: [{ entity_type, id, changes, updated_at }]`. Supports student, attendance, classroom with conflict check. |
| **REPLAY_SYNC_BATCH** | Done | SW message `REPLAY_SYNC_BATCH` with `limit`; replays up to N items per type (drip). Status bar uses it when user clicks “Sync now” and drip mode is on. |
| **Entity/requests sync toggles** | Done | `offline_entity_sync`, `offline_requests_sync` in default_backend_feature_flags; Feature Control toggles; SW uses `entitySyncEnabled` / `requestsSyncEnabled` in `isApiWriteAllowedByToggles`. |
| **reachability_url in default flags** | Done | `reachability_url`, `offline_entity_sync`, `offline_requests_sync` in `default_backend_feature_flags`. |
| **Auto-Pilot (prefetch)** | Done | `GET /api/offline/prefetch_urls/` returns role-based URLs; `static/js/auto-pilot.js` fetches list and prefetches each URL (SW caches). Runs on interval when connection is 4g/5g. |
| **On-device OCR – correction store** | Done | `SMSOfflineDB.addOcrCorrection(original, corrected)` and `getOcrCorrection(original)`; store `ocr_corrections` in offline-db. Use with Tesseract.js to “learn from corrections.” |
| **Local Hub mode** | Done | `docs/LOCAL_HUB_MODE.md`: deployment outline, hub URL, optional SW fallback. |
| **Queue/draft encryption** | Done | `docs/OFFLINE_ENCRYPTION_AND_KEYS.md`: key storage, rotation, wiring to SW and form-draft-save hooks. |
| **Per-form offline note** | Done | FormDraftSave already injects `.sms-offline-form-hint` with “Your changes are saved locally and will sync when you’re back online.” (or `data-offline-hint`). |
| **E2E authenticated flow** | Done | `offline-sync.spec.js`: login (env TEST_USERNAME/TEST_PASSWORD), go offline, online, click Sync now if visible. |
| **Offline replay_batch route** | Done | `path('offline/replay_batch/', OfflineReplayBatchAPI.as_view())` in `apps/api/urls.py`. |
| **Server unreachable in bar** | Done | Persistent orange “Server unreachable” state in status bar until reachability succeeds or user goes offline. `offline-status-bar.js`: `serverUnreachable`, `setServerUnreachable`. |
| **FormDraftSave on more forms** | Done | Request action form (`requests/detail.html`), access request form (`requests/access_denied.html`), support request form (`portal/support_request.html`) use `data-draft-key` and `FormDraftSave.init(form)`. |
| **Full E2E submit→sync→assert** | Done | `offline-sync.spec.js`: login, go offline, POST to `/api/attendance/` (queued), go online, Sync now, assert bar shows “Connected” or “Last synced”. |
| **Idempotency for payments** | Done | `PaymentViewSet.create`: `X-Idempotency-Key` header; cached response returned for same key within 24h (`apps/finance/api_views.py`). |
| **Local Hub SW fallback** | Done | When main-origin fetch fails, SW retries with `OFFLINE_CONFIG.hubBaseUrl` + path. Config: `hub_base_url` in `default_backend_feature_flags`; `portal_base.html` passes `hubBaseUrl`. |
| **Auto-Pilot 2 AM / scheduled** | Done | `prefetchAtHour` in config (e.g. 2); `auto-pilot.js` runs prefetch only at that hour and schedules next run at next 2 AM. Backend flag `prefetch_at_hour`. |
| **Queue metrics API** | Done | `GET/POST /api/offline/queue_metrics/`: GET returns last stored metrics; POST accepts `{ total, by_type }` and stores in cache. Status bar POSTs metrics when it receives queue-length. |
| **“Works offline” badge** | Done | FormDraftSave injects a badge at the top of forms with `data-draft-key` when offline mode is enabled (`form-draft-save.js`, class `sms-offline-works-badge`). |
| **Offline-first reads (one page)** | Done | Take student attendance page shows an offline-only message with cached classroom/student counts from SMSOfflineDB when offline (`roll_call_student.html`). |
| **Conflict resolution modal** | Done | Modal lists failed items and adds a short “How to resolve” step list; “Dismiss list” clears the list from the bar (`offline_status_bar.html`). |
| **Sync health in backend** | Done | Backend dashboard status fragment shows “Offline queue (last reported): N” when offline mode is on and metrics exist (`backend_dashboard_status_fragment`, `accounts/views.py`). |
| **Teacher roll call offline notice** | Done | Take teacher attendance page shows an offline-only message when offline (`roll_call_teacher.html`). |
| **Multi-tab sync** | Done | BroadcastChannel `sms-offline-sync`: when one tab runs Sync now, others show “Syncing in another tab” and disable the button; sync-idle when complete (`offline-status-bar.js`). |
| **Prefetch calendar/lesson URLs** | Done | PrefetchUrlsAPI includes `/portal/calendar/` for admin+teacher; teachers also get `/portal/teacher/timetable/`, `/portal/teacher/lesson-notes/` (`offline_replay_views.PrefetchUrlsAPI`). |
| **Export queue (debug)** | Done | With `?offline_debug=1`, status bar shows an “Export queue” button that copies queue JSON to clipboard (up to 500 items). SW limit for GET_QUEUE_ITEMS raised to 500. |
| **FormDraftSave parent contact** | Done | Parent contact school form (`parent/contact_school.html`) uses `data-draft-key="parent_contact_school"` and `FormDraftSave.init(form)`. |
| **E2E API reachable after sync** | Done | Full-flow E2E asserts GET /api/attendance/ returns 200/401/403 after sync to confirm API is reachable. |

---

## Backend versioning and idempotency

- **Entity API**: Already supports `X-Client-Updated-At` and 409 conflict (apps/api/entity_api.py).
- **Requests**: `AccessRequest` has `updated_at`; use same pattern for conflict if you add a requests REST API.
- **Idempotency for payments**: Implemented. `PaymentViewSet.create` accepts `X-Idempotency-Key`; same key within 24h returns cached response.

---

## File reference

- **Service worker:** `static/js/service-worker.js` (queue, replay order, REPLAY_SYNC_BATCH, entity/requests toggles, precache)
- **Offline mirror:** `static/js/offline-db.js` (includes ocr_corrections), `static/js/vendor/dexie.min.js`
- **Sync orchestration:** `static/js/sync-manager.js` (requestSyncBatch, sendDeltaBatch)
- **Low power:** `static/js/low-power.js`, `static/css/reduce-motion-low-power.css`
- **Auto-Pilot:** `static/js/auto-pilot.js`; API `apps/api/offline_replay_views.PrefetchUrlsAPI`
- **Delta API:** `apps/api/sync_delta_api.py`; route `/api/offline/delta/`
- **Queue metrics:** `apps/api/offline_replay_views.QueueMetricsAPI`; route `/api/offline/queue_metrics/`
- **Docs:** `docs/OFFLINE_ENCRYPTION_AND_KEYS.md`, `docs/LOCAL_HUB_MODE.md`
- **Status bar:** `static/js/offline-status-bar.js` (drip + batch on Sync now, server unreachable state, POST queue metrics)
- **Config:** `portal_base.html` (SMS_OFFLINE_CONFIG), `apps/siteconfig/models.py`, `views_feature_control.py`
- **E2E:** `tests/e2e/offline-sync.spec.js`

---

## Quick verification

1. **Replay order:** DevTools → Application → Service Workers; “Sync now” → attendance then grade then api in network tab.
2. **Delta:** `POST /api/offline/delta/` with `{ "items": [{ "entity_type": "student", "id": 1, "changes": { "first_name": "X" }, "updated_at": "..." }] }` (auth required).
3. **Batch replay:** When drip on, click “Sync now” → SW receives REPLAY_SYNC_BATCH with limit 10.
4. **Prefetch:** With offline mode on, open portal; after ~5s auto-pilot fetches `/api/offline/prefetch_urls/` and prefetches returned URLs.
5. **OCR corrections:** `SMSOfflineDB.addOcrCorrection('ocr text', 'corrected'); SMSOfflineDB.getOcrCorrection('ocr text')` → `'corrected'`.
6. **Entity/requests toggles:** Disable “Offline Entity Sync” in Feature Control → entity API writes no longer queued when offline.
