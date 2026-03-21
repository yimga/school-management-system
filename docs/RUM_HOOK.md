# Real-user monitoring (RUM) hook

## Enable

1. Set environment variable **`RUM_INGEST_KEY`** to a **random string of at least 16 characters** (same deployment as the app).
2. Redeploy. Portal (`portal_base.html`) and marketing shell (`marketing/base_marketing.html`) will load `static/js/rum-beacon.js`, which posts to **`POST /api/internal/rum/`**.

When `RUM_INGEST_KEY` is unset or too short, the endpoint returns **404** and no script is injected.

## Behavior

- **Beacon timing:** `visibilitychange` (hidden) and `pagehide` — one send per page load (deduplicated).
- **Payload:** JSON with `token` (must match `RUM_INGEST_KEY`), `path`, optional `navigation_type`, and `metrics` (allowlisted keys: `lcp`, `cls`, `inp`, `fcp`, `ttfb`, `fid`, `tbt`, `nav`).
- **Auth:** Token in body supports `navigator.sendBeacon` (custom headers are unreliable). Optional header `X-RUM-Key` is also accepted.
- **Limits:** Request body max **4 KiB**; **120 requests/hour per IP** (Django cache).
- **Audit:** Each accepted beacon emits **`rum_web_vitals`** to `PlatformEventLog` (see `EVENT_CATALOG`).

## Operations

- Rotate `RUM_INGEST_KEY` if the value is exposed; old beacons will 403 until clients load a new page with the new token.
- For staging Lighthouse extras, see [LHCI_STAGING_GITHUB_VARS.md](LHCI_STAGING_GITHUB_VARS.md).

## Staff read path (N10)

**`GET /api/internal/north-star/rum-web-vitals/`** (authenticated **staff or superuser** only) returns JSON:

- `beacon_count`, `window_hours`, `paths_top`, per-metric `n` / `p50` / `p95` for allowlisted keys
- `rum_ingest_configured` — whether `RUM_INGEST_KEY` is set (≥ 16 chars), without exposing the secret

Linked from **`GET /api/internal/br/slo-targets/`** under `observability.rum_web_vitals_summary`.

## Tests

- `apps.platform_runtime.tests.test_rum_ingest`
- `apps.platform_runtime.tests.test_rum_aggregate`
- `apps.api.tests.test_north_star_api_views` (RUM summary RBAC)
