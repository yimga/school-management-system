# Resilient Edge – Completion Checklist

One-page sign-off checklist for the offline-first PWA (Resilient Edge) implementation.  
See [RESILIENT_EDGE_IMPLEMENTATION_STATUS.md](RESILIENT_EDGE_IMPLEMENTATION_STATUS.md) for full details.

---

## Features delivered

| Area | Delivered |
|------|-----------|
| **Service worker** | Queue, replay order (attendance → grade → api), batch/drip replay, hub fallback, entity/requests toggles |
| **Offline mirror** | Dexie: students, attendance, classrooms, evaluations, OCR corrections; hydration + post-sync refresh |
| **Sync** | Sync manager (Sync now, requestSyncBatch, sendDeltaBatch), drip mode, hydrateAfterSync |
| **APIs** | Delta, replay_batch, prefetch_urls, queue_metrics; idempotency for payments |
| **UX** | Reachability, low power, server-unreachable state, conflict resolution modal, “Works offline” badge |
| **Prefetch** | Role-based URLs, calendar/lesson URLs, 2 AM prefetch window (configurable) |
| **Forms** | FormDraftSave: marks entry, split allocation, request action, access request, support request, parent contact school |
| **E2E** | Offline fallback, auth flow, full flow (queue → sync → bar + API reachable) |
| **Extras** | Multi-tab (BroadcastChannel), export queue (`?offline_debug=1`), sync health in backend strip, offline-first notices (student/teacher roll call) |

---

## Quick verification (sign-off)

- [ ] **Offline fallback:** Visit `/offline/` → “Sync now” and “When back online” visible.
- [ ] **Status bar:** With offline mode on, portal shows connection bar (Connected / Offline – N items / Syncing…). Click “Sync now” when online.
- [ ] **Replay order:** DevTools → Application → Service Workers; click “Sync now” → Network shows attendance then grade then api.
- [ ] **Drip mode:** With weak connection or Save Data, “Sync now” uses batch (no auto-replay on going online).
- [ ] **Server unreachable:** With server down or unreachable URL, bar shows orange “Server unreachable” until success or offline.
- [ ] **Form draft:** On a FormDraftSave form (e.g. marks entry), see “Works offline” badge and offline hint; draft restores on reload.
- [ ] **Multi-tab:** Two portal tabs open; click “Sync now” in one → other shows “Syncing in another tab” until done.
- [ ] **Backend sync health:** Backend dashboard (with offline mode on) shows “Offline queue (last reported): N” in status strip when metrics exist.
- [ ] **E2E:** Install browsers once: `npx playwright install`. Set `TEST_USERNAME` and `TEST_PASSWORD` for authenticated tests. Run `npm run test:e2e` (or `npx playwright test tests/e2e/offline-sync.spec.js`) → all tests pass.

---

## Optional / not implemented (documented)

- Client-side delta from mirror (diff + sendDeltaBatch).
- Production queue/draft encryption (Web Crypto + server key).
- Full on-device OCR UI (Tesseract.js + camera).
- Per-workflow pending registry, push-based prefetch.

See [RESILIENT_EDGE_WHATS_LEFT_AND_NICE_TO_HAVE.md](RESILIENT_EDGE_WHATS_LEFT_AND_NICE_TO_HAVE.md).

---

## Live deployment: variables

**No new environment variables are required** for the Resilient Edge (offline) code on live. All of the following are driven by the **database** (SiteSettings and backend feature flags), not by env vars:

- **Offline mode on/off:** `SiteSettings.enable_offline_mode` (default `True`). Toggle in Django admin (Site settings) or Feature Control.
- **Status bar, form queue, attendance/grade/entity/requests sync, low power, etc.:** `backend_feature_flags` (e.g. `show_offline_status_bar`, `enable_offline_form_queue`, `reachability_url`, `hub_base_url`, `prefetch_at_hour`). Configure in **Feature Control** or Site settings → Backend feature flags.

Optional flags you can set in admin for live (if you use them):

| Flag | Use |
|------|-----|
| `reachability_url` | Custom health URL for "Sync now" (default `/health/`). |
| `hub_base_url` | Local Hub fallback origin when main server is unreachable. |
| `prefetch_at_hour` | Hour (0–23) for scheduled prefetch (e.g. 2 for 2 AM). |

**E2E tests only** (not for live): set `TEST_USERNAME` and `TEST_PASSWORD` when running Playwright; `BASE_URL` in Playwright config defaults to `http://localhost:8000`.

---

## Sign-off

| Role | Name | Date |
|------|------|------|
| Implementation | | |
| QA / Verification | | |
| Product / Owner | | |
