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

## Load balancer & platform liveness

**Purpose:** Give operations a single reference for HTTP probes (Kubernetes / cloud LB / synthetic checks). Implemented in `config/urls.py` (`apps.observability.views`).

| Path | Name (reverse) | Typical use |
|------|----------------|-------------|
| `GET /health/` | `health` | **Primary LB probe** — public liveness (`public_health`). |
| `GET /ready/` | `ready` | Same handler as `/health/`; use when you want a separate **readiness** URL in orchestration. |
| `GET /healthz/` | `healthz` | Lightweight/alternate probe name. |
| `GET /status/` | `status` | Alias for public health (monitoring dashboards). |
| `GET /api/health/` | `api_health` | JSON-oriented health (API-style consumers). |

**Configure:** Point load balancers and uptime monitors at **`/health/`** or **`/ready/`** on the app origin (no auth). For dependency-aware readiness (DB/Redis), extend `public_health` / `api_health` in code and document new behavior here.

**Cross-ref:** [SOT §0.1.5 Serious — SLO/smoke](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md); [RUNMYCAMPUS §0.1.4](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) simple hygiene row (LB item closed when this section exists).
