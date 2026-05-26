# Offline Mode: Platform-Wide Strategy and Data Integrity

**Execution program (2026-05-23):** Multi-wave build plan at [`docs/plans/SOVEREIGN_OFFLINE_ONLINE_DELIVERY_PLATFORM_PLAN.md`](plans/SOVEREIGN_OFFLINE_ONLINE_DELIVERY_PLATFORM_PLAN.md) (SOT batch **1405**, implementation **1406–1412**). This doc remains the strategy reference; the plan owns wave deliverables and verifiers.

This document describes how to extend offline support to **every component, module, app, and workflow** on the platform, and how to **preserve data integrity** when multiple staff work concurrently (some offline, some online).

---

## 1. Current State (What Has Offline Support Today)

| Area | Offline support | Mechanism |
|------|-----------------|-----------|
| **Attendance** | Yes | Service worker queues `/api/attendance/`; roll-call forms use `data-rmc-offline-form="attendance"` + `rmc-offline-portal-forms.js`. |
| **Grades / mark entry** | Yes | SW `/api/grades/`, `/api/evals/`; portal forms `grading` + `form-draft-save.js`. |
| **Payments / receipts** | Yes | `payment_receipt` on invoice detail; SW `/api/finance/`; `OfflinePaymentIntent` bursar queue. |
| **Notes / forums / bulk capture** | Yes | `notes_report` typed forms + server `_apply_notes_report`. |
| **Support / parent contact** | Yes | `support_ticket` → `GlobalSupportTicket` on sync. |
| **Schoolops / finance / payroll POST forms** | Yes | `data-rmc-offline-form="field_capture"` queues JSON; on sync, `offline_workflow_apply` runs **schoolops** (handover, lost-belongings), **finance** workflows (cash closure, suspense claim, access bulk/request, report request, split allocation, permission-to-pay, etc. via `FinanceOfflineCaptureRecord`), and **payroll** (`payroll_create_run`, `payroll_leave_request` via `PayrollOfflineCaptureRecord`). Batch jobs (generate fees, OCR scan teller) queue as `PENDING_REVIEW` until online. |
| **Entity / requests REST writes** | Partial | SW queues `/api/entity/`, `/api/entities/`, `/api/requests/` when toggles on; conflict UX varies by API. |
| **Read mirror (rosters)** | Partial | `offline-db.js` (Dexie) + `sync-manager.js` hydrate on load/sync; roll-call uses `data-attendance-offline-hydrator`. |
| **Delta sync** | Yes | `POST /api/offline/delta/` wired via `SMS_OFFLINE_CONFIG.deltaEndpointUrl`. |
| **IAM offline** | Yes | Signed snapshot + `POST /api/offline/iam_intent/` (not `OfflineAction` enqueue). |
| **Reachability** | Yes | `/health/` or tenant `reachability_url`; hub retry via `hubBaseUrl` on hybrid/edge. |

Typed portal forms and the service worker cover **field-critical writes**. Handover packets and lost-belongings tags are **persisted on sync** (batch 1510); anonymous finder lookup resolves `short_code` from the database. Live payment-rail authorize still requires connectivity.

---

## 2. Making Offline Available for Every Component, Module, App, and Workflow

### 2.1 Principles

- **Single queue, many sources**: Prefer one offline queue (service worker IndexedDB + optional form-draft for long forms) that any module can push into.
- **API-first**: Where a workflow is driven by REST (e.g. `/api/entity/finance/`, `/api/requests/`), the service worker can intercept failed writes and queue them; replay when online.
- **Forms that are not yet API**: Use the **form-draft-save** pattern (draft + pending submissions in localStorage, sync when online) so every form can work offline.

### 2.2 Option A: Extend the Service Worker Queue (Recommended for API Writes)

**Current:** `static/js/service-worker.js` only queues requests to `/api/attendance/` (`isApiWriteRequest` / `inferSyncType`).

**To support all modules:**

1. **Add more paths** in `isApiWriteRequest` and `inferSyncType`:
   - `/api/entity/` (finance, attendance, student, etc.)
   - `/api/requests/`
   - `/api/evals/` or grade/mark endpoints if they become REST
   - Any other write API your app uses.

2. **Sync type strategy:**
   - Either one **generic** type (e.g. `"api"`) so one replay sends all queued requests in order, or
   - Per-domain types (`"attendance"`, `"grade"`, `"finance"`, `"request"`) if you need separate Background Sync tags or ordering rules.

3. **Replay order:** Replay in `createdAt` order so that dependent writes (e.g. create then update) stay in order. The current `replayQueue(syncType)` already processes items in order per type.

4. **Feature Control:** Keep toggles (e.g. "Offline Attendance Sync", "Offline Grade Sync") and add toggles for new areas (e.g. "Offline Finance Sync", "Offline Request Sync") so admins can enable/disable per domain.

**Example** (conceptual) in `service-worker.js`:

```js
function isApiWriteRequest(request, url) {
  if (!["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) return false;
  if (url.pathname.startsWith("/api/attendance/")) return true;
  if (url.pathname.startsWith("/api/entity/")) return true;
  if (url.pathname.startsWith("/api/requests/")) return true;
  // Add more as needed
  return false;
}
function inferSyncType(pathname) {
  if (pathname.startsWith("/api/attendance/")) return "attendance";
  if (pathname.startsWith("/api/entity/")) return "api";  // or "finance", "entity", etc.
  if (pathname.startsWith("/api/requests/")) return "api";
  return "api";
}
```

Then ensure `replayQueue("api")` (and any new type) is called in the `sync` event handler and in the `REPLAY_SYNC_NOW` message handler.

### 2.3 Option B: Form-Draft-Save for Every Form (Non-API or Legacy Forms)

For pages that submit via full form POST (not fetch to `/api/...`):

- Use **FormDraftSave** (or the same pattern): save draft to localStorage, and when the user submits while offline, append to a **pending submissions** list (keyed by form or workflow).
- On `online` (and after reachability check), show "Submit draft now" / "Sync now" and POST each pending submission in order.
- This is already implemented for grade/mark entry; the same pattern can be applied to finance forms, request forms, compliance forms, etc., by initializing `FormDraftSave.init(form)` and using a unique draft key per form/workflow.

### 2.4 Option C: Central Offline Queue API (Advanced)

- Expose a small **client API** (e.g. `window.SMSOfflineQueue.enqueue(method, url, body)`).
- Any component (React, Django template, or shared JS) calls this instead of `fetch()` when it wants offline-safe writes.
- The implementation can push into the same IndexedDB queue the service worker uses, and the service worker replays when online (or the page can trigger `REPLAY_SYNC_NOW` after reachability check).

Extending the service worker (Option A) plus form-draft for non-API forms (Option B) is usually enough to cover "every component"; Option C is optional for a unified API.

### 2.5 Checklist for Adding a New Module to Offline

1. **If the module uses REST (fetch to `/api/...`):** Add the path and sync type in `service-worker.js` (`isApiWriteRequest`, `inferSyncType`, `sync` and `REPLAY_SYNC_NOW` handlers). Add a Feature Control toggle if desired.
2. **If the module uses form POST:** Integrate FormDraftSave (draft + pending list) and a "Sync now" / "Submit draft now" flow when online.
3. **Ensure server-side:** Accepts idempotent or version-aware requests where needed (see data integrity below).

---

## 3. Data Integrity: Multiple Staff Online and Offline at Once

When several people use the system at the same time—some online, some offline—you must avoid corrupt or inconsistent data.

### 3.1 Strategies to Use

| Strategy | What to do | Where |
|----------|------------|--------|
| **1. Version / optimistic locking** | Store a version field (e.g. `version` or `updated_at`) on entities. On sync or update, send it; server rejects if the stored version is older than current (someone else changed it). | Models (Django), API serializers, and sync payloads. |
| **2. Last-write-wins (LWW) with timestamp** | Already used for attendance (`updated_at`). Server can compare client timestamp vs server; accept or reject. | Attendance sync, evals; extend to other domains. |
| **3. Conflict resolution policy** | Decide per domain: **reject** (force user to refresh and re-apply), **auto_merge** where safe, or **show_both** and let user choose. SiteSettings already has `offline_sync_conflict_resolution`. | Sync endpoints, evals conflict UI. |
| **4. Server-side validation** | Always validate and authorize on the server. Never trust client for business rules or uniqueness. | All API views and sync batch endpoints. |
| **5. Idempotency keys** | For critical writes (e.g. payments), client sends an idempotency key; server deduplicates and returns the same result for the same key. | Finance, payments, and any high-value write. |
| **6. Ordering** | Replay queued requests in **creation order** (`createdAt`) so that "create then update" and "create A then create B" stay consistent. | Service worker `replayQueue` (already ordered). |
| **7. Transactions where needed** | For multi-step operations (e.g. create invoice + payment), use DB transactions so either all steps commit or none. | Django views/sync endpoints. |
| **8. Unique constraints** | Enforce uniqueness in the DB (e.g. one attendance per student/date/session). Sync that would duplicate is rejected; client can show conflict. | Models and migrations. |

### 3.2 Concrete Improvements

- **Attendance:** Already uses `updated_at` and sync batch; keep rejecting or merging based on timestamp and conflict resolution setting.
- **Evals/grades:** Already has `OfflineSyncService` and conflict resolution view; ensure all grade sync paths use version/`modified_at` and the same conflict policy.
- **Finance / entity / requests:** When adding offline queue for these:
  - Add `updated_at` or `version` to models if not present; include in API and sync payloads.
  - In sync/update views: compare client version with DB; return 409 or a structured conflict if stale.
  - Optionally add idempotency keys for payments or other critical writes.
- **Reachability:** Already implemented: "Syncing…" and "Sync now" only after a successful reachability check to `/health/`, reducing false "synced" when the server is unreachable (e.g. LAN only).

### 3.3 What to Avoid

- **Don’t** rely only on client-side checks for conflicts.
- **Don’t** replay writes in random order; keep `createdAt` order.
- **Don’t** assume `navigator.onLine` means the server is reachable; use the reachability check (e.g. `/health/`) before showing "Syncing…" or triggering sync.

---

## 4. Reachability Check (Implemented)

- **When:** The portal runs a **reachability check** when the browser fires the `online` event, and before running "Sync now".
- **How:** `offline-status-bar.js` calls `checkReachability()` which does a `GET` to **`/health/`** with `cache: 'no-store'` and a 5s timeout.
- **Behaviour:**
  - **On `online`:** Only if the check succeeds do we show "Syncing…" and rely on Background Sync; otherwise we show "Connected" and do not imply sync.
  - **On "Sync now":** If the check fails, we show "Server unreachable", dispatch `sms-sync-unreachable`, and a toast suggests syncing when the connection is restored.
- **Config:** `SMS_OFFLINE_CONFIG.reachabilityUrl` can override the URL (default `/health/`).

This avoids showing "Syncing…" when the device is on LAN but the server is not reachable.

---

## 5. Summary

- **Platform-wide offline:** Extend the service worker’s queue to all relevant API write paths (Option A), and use the form-draft-save pattern for non-API forms (Option B). Use the checklist in 2.5 when adding a new module.
- **Data integrity:** Use versioning/optimistic locking, LWW with timestamps, conflict resolution, server-side validation, idempotency where needed, ordered replay, and transactions. Avoid trusting only the client or replaying out of order.
- **Reachability:** Rely on the implemented reachability check so "Syncing…" and "Sync now" only run when the server is actually reachable.

See also: `docs/OFFLINE_MODE_AUDIT.md` for current implementation details, and `static/js/service-worker.js` and `static/js/offline-status-bar.js` for the code.
