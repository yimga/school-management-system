# Observability and SLO for Platform Health

> **CONSOLIDATED — read [OBSERVABILITY.md](OBSERVABILITY.md) + [OBSERVABILITY_SLO_CODE.md](OBSERVABILITY_SLO_CODE.md) first.**
> Per the 2026-05-17 12-pillar audit (P10 doc-hygiene), the canonical pair for SLO + observability content is `OBSERVABILITY.md` (foundation / debugging / on-call) and `OBSERVABILITY_SLO_CODE.md` (SLO code SOT pointing to [`apps/observability/slo.py`](../apps/observability/slo.py)). This file is retained for historical references; new SLO targets and dashboard prose belong in the canonical pair.

**Purpose:** Single place for platform operators to find SLO dashboards, health checks, and runbooks.

---

## SLO dashboard

- **Endpoint:** `GET /api/observability/slo-dashboard/` (JSON) or `?format=html` for rendered view.
- **Control-plane entry:** From `/super/health/` (control health dashboard), link to **SLO dashboard**.
- **Settings:** Configure targets in Django settings:
  - `WEBHOOK_SUCCESS_SLO_PERCENT` (default 99.0)
  - `WEBHOOK_P95_LATENCY_SLO_MS` (default 15000.0)
  - `SYNC_CONFLICT_PENDING_SLO_MAX` (default 10)
- **Tests:** `apps/observability/test_slo_dashboard_api.py`.

---

## Health checks

- **Pulse:** `/super/pulse/` — platform pulse / tenant activity.
- **Control health:** `/super/health/` — control-plane health hub (runbooks, SLOs, incidents, tenant health).
- **Tenant health:** `/super/tenant-health/` — per-tenant health.
- **App health:** `/healthz`, `/metrics` (observability app).

---

## Incidents and monitoring

- **Models:** `PlatformIncident`, `SystemHealthMetric`, `HealthCheckAlert`, `PerformanceTrace`, `AnomalyDetection` (observability app).
- **Runbooks:** Document in this repo or linked runbook repo; link from migration cloud and health hub.

---

**See also:** `GOVERNANCE_FEATURE_TOGGLES_AND_PACKS.md`, control-plane templates.
