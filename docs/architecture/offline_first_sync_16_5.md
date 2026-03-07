# Offline First and Sync Engine (Section 16.5)

Teachers can do attendance, grade entry, and notes offline; sync engine resolves conflicts.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 16.5.

---

## 1. Policy

- **offline_mode:** Policy or feature flag can enable offline-capable flows for a school (e.g. attendance, grade entry). When enabled, UI and API support queuing changes when offline and replay when online.

---

## 2. Existing pieces

- **Offline replay API:** `apps.api.offline_replay_views` — OfflineReplayBatchAPI, PrefetchUrlsAPI, QueueMetricsAPI. Batch replay of queued actions when back online.
- **Delta sync:** `apps.api.sync_delta_api.DeltaSyncAPI` — delta sync for mobile.
- **SyncConflict (siteconfig):** Model for recording sync conflicts when same entity is edited offline and on server.

---

## 3. Sync engine contract

- **Queue:** Client (PWA/mobile) queues mutations (e.g. "mark attendance", "submit grade") in local storage or IndexedDB; when online, POST to replay API with batch.
- **Conflict resolution:** Server applies last-write-wins or returns conflict; client can show "Conflict" and let user choose. SyncConflict model stores conflict details for audit.
- **Idempotency:** Replay requests should carry idempotency keys so duplicate submissions (e.g. retry) do not double-apply.

---

## 4. Implementation status

| Item | Status |
|------|--------|
| Policy offline_mode | Partial (feature flag / policy key) |
| Replay API, delta sync, SyncConflict | Done (existing) |
| Full offline UI (service worker, queue UI) | Partial / deferred |
| Conflict resolution UX | Documented; server-side conflict detection can be extended |
