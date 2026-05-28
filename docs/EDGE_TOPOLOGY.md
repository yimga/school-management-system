# Edge Topology — RunMyCampus v4.00.0

This document is the canonical SOT for the Cloudflare Workers edge layer
introduced in v4.00.0. Ops owns deployment; engineering owns the code.

## What the edge does

Two responsibilities, one Worker:

1. **SWR cache for slow-changing tenant config** at `/edge/runtime/*`.
   The Worker fronts the canonical Django endpoints at
   `/api/v1/runtime/{calendar,grading-matrix,defaults,site-settings,feature-flags}`
   with stale-while-revalidate semantics (15s fresh, 5min revalidate window).
   The `Surrogate-Key` header on each origin response keys the KV bucket;
   `/edge/_purge` accepts HMAC-signed selective invalidation from the Django
   side when `RuntimeDefaults` / `SiteSettings` change.

2. **Authenticated LiteLLM passthrough** at `/edge/llm/*`.
   The Worker injects `X-RMC-Viewport` from CF-Device-Type + Save-Data +
   Downlink, swaps the operator session cookie for the LITELLM_API_KEY
   bearer, preserves chunked transfer-encoding end-to-end. Streaming
   completions arrive at the browser with TTFT measured from the edge POP,
   not the central region.

## File layout

| File | Purpose |
|---|---|
| `edge/wrangler.toml` | CF Workers config |
| `edge/src/worker.js` | The 4-route Worker |
| `services/edge_cache.py` | Django-side Surrogate-Key builder + HMAC purge |
| `services/edge_cache_signals.py` | post_save signal hooks |
| `apps/api/runtime_endpoints.py` | The 5 canonical /api/v1/runtime/* views |
| `apps/api/middleware_edge_fallback.py` | Django-side SWR for single-region deploys |
| `scripts/scan_edge_cache_headers.py` | Static enforcement of Surrogate-Key |

## Deploy procedure (ops)

```bash
cd edge/
npx wrangler@latest kv:namespace create rmc_edge_swr
# Copy the printed id into wrangler.toml under [[kv_namespaces]] id=
npx wrangler@latest secret put LITELLM_API_KEY        # paste secret at prompt
npx wrangler@latest secret put EDGE_HMAC_SIGNING_KEY  # 32+ char random
npx wrangler@latest deploy
```

Then in Django env:

```
RMC_EDGE_PURGE_URL=https://edge.runmycampus.com/edge/_purge
RMC_EDGE_PURGE_HMAC_KEY=<same as EDGE_HMAC_SIGNING_KEY above>
```

DNS: point a hostname (e.g. `edge.runmycampus.com`) at the Worker route
`*/edge/*`.

## Single-region fallback

When Cloudflare is NOT provisioned, set `RMC_EDGE_FALLBACK_ENABLED=1`. The
Django middleware `apps.api.middleware_edge_fallback.EdgeSWRFallbackMiddleware`
mimics the Worker's SWR behavior using the local Django cache. Identical
Surrogate-Key contract, identical 15s/5min window.

This path is intentionally slower than the real edge — it's a deploy
convenience, not a long-term answer.

## Verify

```bash
python scripts/scan_edge_cache_headers.py --compare   # baseline 0
curl -i https://<tenant>.runmycampus.com/api/v1/runtime/calendar
# expect: Surrogate-Key: <tenant>::/api/v1/runtime/calendar::v=A
#         Cache-Control: public, max-age=15, s-maxage=900, stale-while-revalidate=300

curl https://edge.runmycampus.com/edge/_health   # "ok"
```
