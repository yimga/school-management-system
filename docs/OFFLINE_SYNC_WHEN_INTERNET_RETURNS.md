# Offline Mode: Sync When Internet Returns

When the site is **totally offline** then comes back online, these behaviours and **optional improvements** are implemented.

---

## Implemented behaviour

1. **Reachability check** – When the browser fires `online`, the app calls GET `/health/` (configurable). Only if that succeeds do we consider the server reachable.
2. **Auto-trigger sync** – When reachability succeeds, the portal sends `REPLAY_SYNC_NOW` to the service worker so the queue is replayed without the user clicking “Sync now”.
3. **Manual “Sync now”** – Header button triggers the same reachability check, then replay.
4. **Queue visibility** – While offline, the status bar can show **“Offline – N item(s) will sync”** via `GET_QUEUE_LENGTH` (polled every 8s when offline).

---

## Optional improvements (implemented)

| Improvement | Description |
|-------------|-------------|
| **Periodic retry when unreachable** | If the browser goes `online` but reachability fails, we retry reachability every 30s (max 10 times). When it succeeds, we auto-trigger sync and stop retrying. |
| **Last synced at** | On successful sync (`sync-complete` with no failures), we store the time in `localStorage` (`sms-last-synced-at`) and show “Last synced X ago” in the status bar (e.g. “1 min ago”). Refreshed every 60s. |
| **Conflict list UI** | When replay returns 4xx (e.g. 409), the service worker sends `failedItems` (url, status, message) in `sync-complete`. The client appends these to `localStorage` (`sms-sync-conflicts`) and shows a **“Resolve conflicts (N)”** link. Clicking it opens a modal listing each failed item (path + message); user can open the resource and re-apply changes, then **Dismiss** to clear the list. |
| **Exponential backoff on 5xx** | On 5xx or network error during replay, we keep the item in the queue and set `nextRetryAt = now + backoff`. Backoff is `min(2^attemptCount * 2s, 15 min)`. Replay skips items whose `nextRetryAt` is in the future. |
| **Queue length in status bar** | Service worker handles `GET_QUEUE_LENGTH` and replies with `queue-length` (counts per type + total). Status bar shows “Offline – N item(s) will sync” when offline and N > 0. |

---

## Files touched

- **Service worker** (`static/js/service-worker.js`): `GET_QUEUE_LENGTH`, `failedItems` in `sync-complete`, `updateSyncItem`, backoff in `replayQueue`.
- **Status bar** (`static/js/offline-status-bar.js`): periodic reachability retry, last-synced storage/display, conflict storage + “Resolve conflicts” + modal, queue-length request/polling.
- **Template** (`templates/components/offline_status_bar.html`): “Last synced” span, “Resolve conflicts” button, conflicts modal.

---

## Optional / not implemented

- **Batch sync endpoint** – A generic server endpoint that accepts a list of `{ method, path, body }` and replays them in one request (to reduce round-trips when the queue is large). The existing `sync_batch` is for mobile/attendance; SW replay remains per-request.
- **Encryption** of queue and drafts (documented elsewhere).
- **“Last synced” only on full success** – We currently set last-synced only when `failedCount === 0`.

See also: `OFFLINE_MODE_AUDIT.md`, `OFFLINE_MODE_GAPS.md`, `OFFLINE_PLATFORM_AND_DATA_INTEGRITY.md`.
