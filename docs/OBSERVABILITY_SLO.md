# Observability and SLO for Platform Health

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
