# Observability and health

> **CONSOLIDATED — read [OBSERVABILITY.md](OBSERVABILITY.md) + [OBSERVABILITY_SLO_CODE.md](OBSERVABILITY_SLO_CODE.md) first.**
> Per the 2026-05-17 12-pillar audit (P10 doc-hygiene), the canonical pair for observability + health content is `OBSERVABILITY.md` and `OBSERVABILITY_SLO_CODE.md`. This file is retained for historical references; new content belongs in the canonical pair.

**Goal:** Truthful health signals; SLO and logs with trace/request ID; operator dashboard and analytics schema.

## Health endpoints

| Endpoint | Auth | Behavior |
|----------|------|----------|
| `/health/` | None (public) | Returns 200 `{"status": "healthy"}`. No DB/cache; for load balancers and cold starts. |
| `/status/` | None (public) | **Tenant/manager:** same as `/health/` (health endpoint). **Public (apex) host:** marketing trust/uptime page (not health). On apex use **`/health/`** or **`/healthz/`** for health checks. |
| `/healthz/` | Observability auth | DB connectivity check. Returns 500 with error body if DB fails. **Truthful:** does not mask exceptions. |
| `/api/health/` | Varies by config | API health; see observability views. |
| `/super/health/` | Super only | Control-plane health dashboard (super_views.super_control_health_dashboard). |

**Rule:** Health checks that assert dependencies (e.g. DB) must return 5xx on failure and must not swallow exceptions. `healthz` implements this.

## Logs and trace ID

- Add structured logging with request_id or trace_id in middleware where available; document log aggregation and retention for operators.
- Exception handling: critical paths avoid broad `except Exception` without logging; see item 7 and runtime_resolver, tenancy middleware, policies resolver.

## SLO and operator dashboard

- Define SLOs for critical paths (login, runtime resolution, billing) and expose metrics; document alerting when SLO is breached.
- Operator dashboard: tenant count, error rate, latency, migration status — via super dashboard and API v1 super endpoints (pulse, usage, tenant-health).

## Analytics events

- Standardize analytics event schema; ensure key actions emit events with consistent naming and payload. Document in analytics app or platform docs.

## References

- apps/observability/views.py — public_health, healthz
- apps/observability/monitoring.py — detailed health if present
- apps/schools/super_views.py — super dashboard and tenant health
