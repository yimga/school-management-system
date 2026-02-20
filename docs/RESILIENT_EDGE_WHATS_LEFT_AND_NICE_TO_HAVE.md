# Resilient Edge – What’s Left & What Else Can Be Included

Complements [RESILIENT_EDGE_IMPLEMENTATION_STATUS.md](RESILIENT_EDGE_IMPLEMENTATION_STATUS.md). The plan’s core, Phase 2, and documented optionals are done; below is what remains and what you can add next.

---

## What’s left (remaining gaps)

### 1. Client-side delta from mirror (optional enhancement)

- **Done:** Delta API and `sendDeltaBatch()` exist; SW still replays **full** request bodies.
- **Left:** Sync-manager (or specific pages) could **compute diffs** from the Dexie mirror vs current form and call `sendDeltaBatch()` with `{ entity_type, id, changes }` instead of relying only on full-body replay. No code today builds delta payloads from the mirror for entity/attendance edits.

### 2. Full E2E: offline submit → online → Sync → assert record

- **Done:** E2E that logs in, goes offline/online, clicks Sync now.
- **Left:** E2E that (1) submits **attendance or a grade** while offline (form submit or API call that gets queued), (2) goes online, (3) triggers Sync now, (4) **asserts the record exists** (e.g. GET attendance or check DOM). Requires stable test user and possibly fixture data.

### 3. FormDraftSave on more forms

- **Done:** Marks entry and split allocation (finance) use FormDraftSave.
- **Left:** Other critical forms (e.g. request forms, compliance, long finance forms) do not. Add `data-draft-key` and `FormDraftSave.init(form)` to those forms; optionally add per-workflow pending keys so “Sync now” can POST to the right endpoints (see OFFLINE_MODE_GAPS.md).

### 4. Per-workflow pending submissions registry

- **Done:** Pending submissions are stored and replayed; marks and split allocation have dedicated handling.
- **Left:** A small **registry** (e.g. workflow id → { url, method }) so any form can register its pending endpoint and “Sync now” replays each workflow’s pending list to the correct URL. Optional if you only have a few form types.

### 5. Idempotency for payments

- **Done:** Documented as optional in implementation status.
- **Left:** Implement: accept `Idempotency-Key` (or body field) on payment/create endpoints, store key + result, and return the same result for duplicate keys so double Sync doesn’t create duplicate payments.

### 6. Queue/draft encryption – production implementation

- **Done:** Docs in OFFLINE_ENCRYPTION_AND_KEYS.md; SW has `maybeEncryptBody` / `maybeDecryptBody` (currently base64 if key set).
- **Left:** Use **Web Crypto (AES-GCM)** in those hooks and a **server endpoint** (or login flow) that provides a short-lived key. No production key delivery or AES implementation yet.

### 7. Local Hub – SW fallback to hub URL

- **Done:** LOCAL_HUB_MODE.md describes deployment and optional fallback.
- **Left:** Implement: add `hubBaseUrl` to config and in the SW fetch handler, when a request to the main origin fails (network), **retry** with `hubBaseUrl` + same path. Requires CORS/cookie handling for the hub origin.

### 8. Auto-Pilot – scheduled time window (e.g. 2 AM)

- **Done:** Prefetch runs when connection is 4g/5g and on a 6‑hour interval.
- **Left:** Optional **time-based** prefetch (e.g. “prefetch between 2 AM and 4 AM” or “prefetch at 02:00”) via a configurable time window and a client timer or a backend job that pushes “prefetch now” (e.g. push notification or polled flag).

### 9. On-device OCR – full UI with Tesseract.js

- **Done:** Correction store in offline-db (`addOcrCorrection` / `getOcrCorrection`); server-side marksheet OCR exists.
- **Left:** **Browser-based** flow: integrate Tesseract.js (or similar) in a page (e.g. marks entry or “scan registry”), capture image (camera/file), run OCR in the worker/page, apply corrections from the store, then submit structured data (same shape as server OCR) to API or queue. “Learn from corrections” is supported by the store; the missing piece is the UI and OCR run.

### 10. Reachability failure – visible state in status bar

- **Done:** “Sync now” shows “Server unreachable” toast when reachability check fails.
- **Left:** OFFLINE_MODE_GAPS suggests showing an **orange “Server unreachable”** state in the status bar briefly so it’s visible without relying only on the toast.

### 11. Queue/replay metrics (observability)

- **Left:** Optional: expose **queue length** or **replay success/failure counts** to an analytics or admin endpoint (or dashboard widget) so schools can monitor offline sync health.

---

## What else can be included (further ideas)

- **Sync health in admin** – Done. Backend dashboard status strip shows “Offline queue (last reported): N” from the stored queue metrics when offline mode is enabled.
- **Conflict resolution UI** – Done. Modal lists failed items with a short “How to resolve” (open page, re-apply changes, Dismiss list). Full server-vs-client merge UI remains optional.
- **“This form works offline” badge** – Done. FormDraftSave injects a small badge (“Works offline”) at the top of forms that have `data-draft-key` when offline mode is enabled (`static/js/form-draft-save.js`).
- **Offline-first reads from mirror** – Done (one page). Take student attendance (`portal/roll_call_student.html`) shows an offline-only notice with cached classroom and student counts from SMSOfflineDB when the user is offline and the mirror is available.
- **Prefetch calendar/lesson URLs** – Done. PrefetchUrlsAPI returns `/portal/calendar/` for admin and teacher; teacher also gets `/portal/teacher/timetable/`, `/portal/teacher/lesson-notes/`.
- **Periodic / scheduled sync** – Use a timer (or Background Sync if you add a periodic pattern) to run prefetch or sync at a **configurable time** (e.g. 2 AM) in addition to the current interval.
- **Push-based prefetch** – Server sends a push notification “prefetch these URLs” so the client doesn’t need to poll; useful for 2 AM or event-driven prefetch.
- **Multi-tab behaviour** – Document or enforce that only one tab “leads” sync (e.g. via BroadcastChannel or shared worker) so multiple tabs don’t double-replay or conflict on hydration.
- **TypeScript / React** – If you add a React/TS front end: add `db.ts` and `syncManager.ts` as typed wrappers over the same Dexie DB and sync behaviour.
- **Vite/Next PWA** – If the app (or part of it) moves to Vite/Next, use their PWA plugin for precache and consider Workbox for more advanced caching strategies.
- **Export/import queue (debug)** – Done. With `?offline_debug=1` the status bar shows “Export queue”; click copies queue JSON to clipboard (support/debug).

---

## Summary

| Category | Status |
|----------|--------|
| **Plan core + Phase 2 + optionals** | Implemented (see RESILIENT_EDGE_IMPLEMENTATION_STATUS.md). |
| **Remaining gaps** | Optional: client-side delta from mirror, production encryption (Web Crypto), full on-device OCR UI, per-workflow pending registry. E2E/FormDraftSave/hub/2 AM/reachability/queue metrics done. |
| **Nice-to-have / future** | Push-based prefetch, TS/React wrappers, Vite/Next PWA. Sync health, conflict UI, offline-first reads, calendar prefetch, multi-tab, export queue done. |

You can prioritise by impact: e.g. **FormDraftSave on more forms**, **full E2E submit→assert**, and **reachability state in bar** for reliability and visibility; **on-device OCR UI** and **prefetch at 2 AM** for the original scenarios; **idempotency** and **encryption** for safety and compliance.
