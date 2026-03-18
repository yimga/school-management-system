# SLO targets & observability (BR-01)

**Definition of done:** Documented p50/p99 targets, dashboard URL, settings keys, CI hook reference.

## Targets

| Surface | p50 | p99 | Evidence |
|---------|-----|-----|----------|
| OneRoster GET (hot paths) | 200ms | 2s | `PERFORMANCE_BUDGETS.md`; metrics via middleware where enabled |
| LTI launch redirect | 150ms | 1.5s | Section 8 / observability |
| `/api/v1/*` auth boundary | 100ms | 1s | `test_api_v1_route_contract` |
| Webhook delivery success | ≥99% | p95 latency ≤15s | `WEBHOOK_SUCCESS_SLO_PERCENT`, `WEBHOOK_P95_LATENCY_SLO_MS` |

## Dashboard

- **Staff/observability:** `GET /api/observability/slo-dashboard/?format=html&hours=24`
- **JSON:** `?format=json` for automation
- **Control plane:** Trust center → SLO & uptime card → Health hub

## CI

- `PERFORMANCE_BUDGET_GATE=1` + `scripts/check_performance_budgets.py` when k6/prod metrics export exists.
- Until then: **release review** this doc + dashboard screenshot.
