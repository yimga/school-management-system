# Offline / local-first mode – implementation audit

This audit checks the codebase against the Cameroon / low-connectivity requirements (local-first storage, sync-later, conflict resolution, PWA, status UI). Reference: user-provided offline-first strategy and Django refactor instructions.

---

## Summary

| Area | Status | Notes |
|------|--------|--------|
| **Local storage / queue** | Done | IndexedDB in service worker (`syncQueue`); localStorage for form drafts and pending mark submissions |
| **Background sync** | Done | Service worker `sync` event; replay by tag (`attendance-sync`, `grade-sync`, `offline-sync-all`); configurable via Feature Control |
| **Conflict resolution** | Done | `offline_sync_conflict_resolution`: reject / auto_merge / show_both; attendance uses `updated_at`; evals use `OfflineSyncService` + manual resolve view |
| **PWA / Service worker** | Done | `static/js/service-worker.js`; CacheFirst for static; NetworkFirst for `/api/` GET; offline fallback `/offline/` |
| **Persistent storage** | Done | `navigator.storage.persist()` called in `portal_base.html` when `requestPersistentStorage` flag set |
| **Django as API for sync** | Done | `OfflineSyncViewSet`, `OfflineSyncQueue`, `/api/sync/`; attendance and grade sync in `mobile_api.py` |
| **Versioning (modified_at)** | Done | Attendance and Evaluation (and others) use `updated_at` / `modified_at`; server compares with client timestamp on sync |
| **Submit override (offline → queue)** | Done | Form draft save (`form-draft-save.js`) stores pending submissions when offline; sync when online; service worker queues `/api/attendance/` writes |
| **Connection status UI** | Done | Global status bar in portal header (Connected / Offline – data will sync later / Syncing…); `offline_status_bar.html` + `offline-status-bar.js`; shown when `SITE.enable_offline_mode`. |
| **Service worker write interception** | Done | Attendance API writes queued; comment in SW for adding grade/eval REST paths if added later. Grade writes use form-draft → sync when online. |
| **API GET strategy** | Done | Stale-While-Revalidate for `/api/` GET (return cached then revalidate in background). |

---

## What is implemented

1. **Feature Control** – Offline Mode, Portal PWA, Offline Form Queue, Offline Attendance Sync, Offline Grade Sync, Background Sync Retry, conflict resolution (reject / auto_merge / show_both), optional persistent storage.
2. **Service worker** – Install/activate; static cache; dynamic cache for API GET; **queue for POST/PUT/PATCH/DELETE to `/api/attendance/`** when offline; replay on `sync` event; navigation fallback to `/offline/`.
3. **Offline page** – `templates/offline.html`, route `/offline/`, “You are currently offline” and note about queued grades/attendance.
4. **API** – `OfflineSyncQueue` model; `OfflineSyncViewSet` (create, sync_batch); attendance sync with `updated_at` comparison; grade sync via `OfflineMarkEntry` and `OfflineSyncService`; conflict handling.
5. **Evals** – `OfflineMarkEntry` model; `OfflineSyncService.sync_offline_entry()`; manual conflict resolution view and template.
6. **Form draft / pending** – `form-draft-save.js`: draft to localStorage, pending submissions list, “Resume draft?”, offline banner, “Saved for sync”, sync when online.
7. **Config** – `SMS_OFFLINE_CONFIG` in `portal_base.html`; `enable_offline_mode`, `offline_sync_conflict_resolution` in SiteSettings; backend feature flags for each toggle.
8. **Persistent storage** – `navigator.storage.persist()` called when `requestPersistentStorage` is enabled.

---

## What is not done (or partial)

1. ~~**Global connection status bar**~~ **Done.** See Summary table: `offline_status_bar.html` + `offline-status-bar.js` in portal header when `SITE.enable_offline_mode`.

2. ~~**Service worker: grade API path (optional)**~~ **Documented.** SW has comment and commented-out branch in `isApiWriteRequest` / `inferSyncType` for future grade/eval REST paths. Web mark entry uses form queue + sync when online.

3. ~~**Stale-While-Revalidate (SWR)**~~ **Done.** API GET uses `staleWhileRevalidateApi` in service worker (return cached then revalidate in background).

4. **Local DB “mirror” (Dexie/PouchDB)**  
   Requirement: “Schema that mirrors Students, Attendance, Grades” and “pre-load when user first logs in.”  
   **Current:** No full client-side mirror of the DB. Queue stores **pending writes** (request body + URL), not a full read-optimized copy of entities.  
   **Impact:** Offline **reading** of full lists (e.g. all students) is limited to whatever was last cached by the SW (API GET cache). Acceptable if the goal is “write offline, sync when back,” not “browse full DB offline.”

5. **Encryption of local data**  
   Requirement: “Keep the local database encrypted (CryptoJS) since school data will sit on local hard drives.”  
   **Current:** IndexedDB and localStorage are not encrypted.  
   **Hook points:** In `service-worker.js`, encrypt before `store.add(item)` in `enqueueSyncItem` and decrypt in `getSyncItems` / when building the fetch body in `replayQueue`. For form-draft-save, encrypt `sms_draft_*` and `sms_pending_mark_submissions` in localStorage. Key source could be a short-lived server token or a user-derived key (Web Crypto API or CryptoJS).  
   **Suggestion:** If policy requires it, implement the above and document key storage (e.g. session-only vs persisted).

6. **Unit test: “Network Down”**  
   **Done:** `apps/api/tests/test_offline_sync.py` – `OfflineSyncBatchTestCase.test_sync_batch_attendance_creates_record` posts `sync_batch` with attendance data and asserts the server creates the Attendance record (simulates “replay after coming back online”). Full browser-offline simulation would require E2E (Playwright/Selenium).

---

## Checklist vs your requirements

| Requirement | Done | Notes |
|-------------|------|--------|
| Local storage (IndexedDB/SQLite) | Yes | IndexedDB in SW; localStorage for drafts/pending |
| Sync-later when online | Yes | SW sync event; form-draft sync when online |
| Conflict resolution (LWW or versioning) | Yes | updated_at comparison; reject / auto_merge / show_both |
| Optimistic UI | Partial | Form draft shows “Saved for sync”; no generic optimistic write UI |
| PWA (cache UI + offline shell) | Yes | SW + /offline/; static + API GET cached |
| Django as REST API for critical flows | Yes | /api/sync/, attendance, OfflineMarkEntry path |
| modified_at on models | Yes | Attendance, Evaluation, etc. have updated_at |
| Submit override (fetch + queue on failure) | Yes | SW queues attendance API; form-draft queues marks |
| Persistent storage (persist()) | Yes | When flag set |
| Connection status bar (Connected/Offline/Syncing) | Yes | Portal header status bar when offline mode enabled |
| Full local mirror DB + hydrate on login | No | Queue-only; no Dexie/PouchDB mirror |
| Local encryption (CryptoJS) | Stub | SW has maybeEncryptBody/maybeDecryptBody (base64 when enableQueueEncryption+queueEncryptionKey); use Web Crypto + server key for production |
| “Network Down” test | Yes | sync_batch attendance test in apps/api/tests/test_offline_sync.py |

---

## Recommended next steps (in order)

1. ~~**Add a global connection status indicator**~~ Done: `templates/components/offline_status_bar.html`, `static/js/offline-status-bar.js`; form-draft-save dispatches `sms-sync-start` / `sms-sync-end`.
2. ~~**Optional: grade/eval write path in SW**~~ Documented; add path in `isApiWriteRequest` / `inferSyncType` if a REST grade/eval write API is added.
3. ~~**Optional: Network Down test**~~ Done: `test_sync_batch_attendance_creates_record` asserts sync_batch creates Attendance.
4. **If policy requires:** Implement encryption at documented hook points (SW `enqueueSyncItem` / form-draft localStorage).
