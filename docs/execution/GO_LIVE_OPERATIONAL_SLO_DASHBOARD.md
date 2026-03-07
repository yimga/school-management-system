# Go-Live Operational SLO Dashboard (SEC-608)

Endpoint:
- `GET /api/observability/slo-dashboard/?hours=24`

Auth:
- Staff/superuser/admin session, or observability API key.

## What It Reports (Per Region)

- Webhook delivery success (`success_rate_percent`)
- Webhook latency (`p95_latency_ms`, breach rate against target)
- Error budget (`remaining_percent`, `burn_percent`)
- Sync conflicts (`pending`, `resolution_rate_percent`)
- Region status (`healthy`, `warning`, `critical`)

## SLO Targets

Defaults (override in settings):
- `WEBHOOK_SUCCESS_SLO_PERCENT` (default `99.0`)
- `WEBHOOK_P95_LATENCY_SLO_MS` (default `15000`)
- `SYNC_CONFLICT_PENDING_SLO_MAX` (default `10`)

## Monitoring Checks

1. `curl -H "X-OBSERVABILITY-KEY: <key>" https://<host>/api/observability/slo-dashboard/?hours=24`
2. Confirm `status=success` and non-empty `regions`.
3. Verify each region row includes:
   - `webhook.success_rate_percent`
   - `webhook.p95_latency_ms`
   - `error_budget.remaining_percent`
   - `sync_conflicts.pending`
4. Alert on:
   - `status=critical`
   - `error_budget.remaining_percent == 0`
   - sustained `sync_conflicts.pending` above target.
