# Offline Mode – What’s Missing in the Codebase

This document lists gaps and improvements for the offline mode implementation. See also `OFFLINE_MODE_AUDIT.md` and `OFFLINE_PLATFORM_AND_DATA_INTEGRITY.md`.

---

## 1. Service worker

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **Replay uses relative URL** | `fetch(item.requestUrl)` with a path like `/api/entity/` is valid in SW but can be fragile if scope/base differs. | Prefer storing and using full URL: `self.location.origin + url.pathname + url.search` when enqueueing and when calling `fetch()` in `replayQueue`. |
| **Stored headers include Cookie / CSRF** | Replay sends **stale** Cookie and X-CSRFToken from the time of the original request. Session may have changed or CSRF rotated → 401/403 on replay. | When serializing, **exclude** `Cookie`, `Authorization`, `X-CSRFToken`, and other auth headers. Rely on `credentials: 'include'` so the browser sends **current** cookies on replay. Optionally refresh CSRF from a controlled client (e.g. postMessage to page to get token) before replay if the API requires it. |
| **4xx responses retried forever** | Only `response.ok` triggers `deleteSyncItem`. 400, 409, 422, etc. leave the item in the queue and it retries on every sync. | On **4xx** (client error): remove from queue (or move to a “failed” store) and optionally notify the user (e.g. `sync-complete` with `{ failed: true }`). On **5xx** or network error, keep in queue for retry. |
| **No replay order guarantee** | `getSyncItems(syncType)` uses index `getAll(syncType)`; order may not be by `createdAt`. | Sort items by `createdAt` (or `id`) before replaying so order is deterministic (create-before-update, etc.). |
| **No queue size limit** | IndexedDB queue can grow without bound if sync keeps failing. | Enforce a max count per `syncType` (or global). When enqueueing, drop oldest items if over limit, or reject new items and surface “queue full” to the user. |
| **No visibility into queue** | Users and admins cannot see how many items are pending. | Optional: expose queue length (e.g. via postMessage to SW and show “N items pending” in the status bar or a small tooltip). |

---

## 2. Form draft / pending (form-draft-save.js)

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **Only marks entry uses it** | No other forms (finance, requests, compliance, long forms) get draft or offline queue. | Add `data-draft-key` and `FormDraftSave.init(form)` to other critical forms (e.g. finance invoice/payment, request forms, compliance). Use a unique key per form/workflow. |
| **Pending key is mark-specific** | `PENDING_SUBMISSIONS_KEY = 'sms_pending_mark_submissions'` and logic are geared to mark entry. | Either keep one key and ensure payload shape is generic, or introduce per-workflow pending keys (e.g. `sms_pending_finance`, `sms_pending_requests`) and a small registry so “Sync now” knows which endpoints to POST to. |
| **No encryption** | Drafts and pending submissions are in localStorage in plaintext. | If policy requires: encrypt before storing (see OFFLINE_MODE_AUDIT.md encryption hook points). |

---

## 3. Backend / API

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **Entity/requests APIs may lack versioning** | When SW replays `/api/entity/` or `/api/requests/`, conflict resolution (LWW, reject, show_both) is not implemented for those endpoints. | Add `updated_at` or `version` to relevant models; in update views, compare client version with DB and return 409 or conflict payload when stale. See OFFline_PLATFORM_AND_DATA_INTEGRITY.md. |
| **No idempotency for critical writes** | Duplicate replays (e.g. double-click Sync) can create duplicate records. | For payments and other critical writes, accept an idempotency key and deduplicate on the server. |
| **Sync batch is mobile/attendance-focused** | `OfflineSyncViewSet` / sync_batch are built for attendance (and evals via OfflineMarkEntry). Entity/requests are replayed as raw HTTP by the SW, not via sync_batch. | Either keep SW replay as raw HTTP (and ensure entity/requests APIs support versioning and auth), or add a generic sync_batch that accepts a list of { method, url, body } and applies conflict rules per resource type. |

---

## 4. UX and copy

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **Offline page doesn’t mention Sync now** | Users on `/offline/` see “Retry Connection” (reload) but not that “Sync now” in the portal header will push queued data once back online. | Add a line: “When back online, open the portal and use **Sync now** in the header to sync queued data.” |
| **No per-page offline hint** | Only the global status bar shows connection state. Long forms don’t say “This form works offline.” | Optional: add a small note on forms that use FormDraftSave: “Your changes are saved locally and will sync when you’re back online.” |
| **Reachability failure is subtle** | If “Sync now” is clicked and server is unreachable, we show “Server unreachable” and a toast; status bar returns to “Connected.” | Consider briefly showing an orange “Server unreachable” state in the bar so it’s visible without relying on the toast. |

---

## 5. Testing and observability

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **No E2E “offline → queue → replay”** | Unit tests cover sync_batch; no browser test that goes offline, queues a write, comes online, and sees it replayed. | Add E2E (e.g. Playwright): load portal, go offline, submit attendance (or entity), go online, trigger Sync now, assert record exists. |
| **No metrics for queue depth / replay** | Hard to see how often sync fails or how large the queue gets. | Optional: expose queue length or replay success/failure counts (e.g. to an analytics or admin endpoint) for monitoring. |

---

## 6. Security and privacy

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **Queue and drafts not encrypted** | IndexedDB queue and localStorage drafts hold sensitive data in plaintext on the device. | If policy requires: use the encryption hooks in the SW and form-draft-save (OFFLINE_MODE_AUDIT.md); document key storage and rotation. |
| **Stale auth in SW replay** | Stored Cookie/CSRF can be replayed; excluding them and using `credentials: 'include'` fixes this. | Implement the header-stripping in the service worker (see Service worker section above). |

---

## 7. Feature Control and config

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **No toggle for “api” sync type** | Entity/requests are queued whenever offline mode is on; no per-domain kill switch. | Optional: add Feature Control toggles (e.g. “Offline entity sync”, “Offline request sync”) and pass them in `SMS_OFFLINE_CONFIG` so the SW only queues when the corresponding flag is on. |
| **reachabilityUrl not in config** | Override is documented but not set in `portal_base.html`. | Optional: add `reachabilityUrl: '{{ SITE.reachability_url|default:"/health/" }}'` (or similar) to `SMS_OFFLINE_CONFIG` if you need per-site URLs. |

---

## 8. Summary checklist

- [x] **SW:** Use full URL in replay; strip Cookie/Authorization/X-CSRFToken from stored headers.
- [x] **SW:** On 4xx remove from queue; sort by `createdAt`; queue size limit (MAX_QUEUE_PER_TYPE). Queue-length visibility optional.
- [x] **Forms:** FormDraftSave extended to split allocation; generic label + `data-draft-pending-label`. Per-workflow pending keys optional.
- [ ] **Backend:** Add versioning/conflict handling for entity and request APIs; optional idempotency for payments.
- [x] **UX:** Offline page copy for “Sync now”; optional per-form offline note.
- [ ] **Testing:** E2E for offline → queue → online → replay.
- [x] **Security:** No stale auth in replay (auth headers stripped). Optional encryption not done.
- [x] **Config:** reachabilityUrl in SMS_OFFLINE_CONFIG. Feature Control toggles for api optional.
