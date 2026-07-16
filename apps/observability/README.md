# apps/observability

> The platform's health story: metrics bridge, SLO registry, Sentry fence,
> incidents, and the public status page.

**Tenancy:** SHARED (public schema; the few tenant-scoped rows carry an explicit `school` FK)
**Scale:** 8 models · 6 migrations · 21 test modules · ~11.8k LOC

## What this app owns

Observability owns how the platform knows it is healthy and how it tells anyone
else. That covers five slices: the pluggable metrics bridge, the SLO registry that
encodes what the platform *promises*, the incident lifecycle (detect → acknowledge →
mitigate → resolve → postmortem), the public `/status/` page, and the structured
logging context that stamps `request_id` / `tenant_id` / `school_id` onto every log
line.

Two decisions matter most. First, this app is a **fence**: `sentry_sdk` may only be
imported inside `apps/observability/` (CI gate `scan_sentry_boundary.py`, baseline 0),
and app code goes through `tracing.py`. The same shape applies to metrics —
`emit_counter` / `emit_gauge` / `emit_histogram` dispatch to a backend chosen by
`OBSERVABILITY_METRICS_BACKEND` (`noop` default, `structured-log`, `prometheus-client`,
`statsd`), so callers never bind to a vendor and a missing library auto-falls back
rather than raising.

Second, **SLOs are code**. `slo.py` holds them as `SLODefinition` rows so a changed
promise shows up as a diff in code review, and `verify_slo_registry.py` gates their
shape in CI.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `SystemHealthMetric` | `observability_systemhealthmetric` | Point-in-time system health metric |
| `HealthCheckAlert` | `observability_healthcheckalert` | Alert raised when a health metric breaches a threshold |
| `PerformanceTrace` | `observability_performancetrace` | Traced operation timing |
| `AnomalyDetection` | `observability_anomalydetection` | Detected anomaly in system behaviour |
| `PlatformIncident` | `observability_platformincident` | Shared-schema incident record with a status FSM; auto-opened/resolved by the sync backlog monitor |
| `IncidentUpdate` | `observability_incidentupdate` | Append-oriented timeline entry for a `PlatformIncident`; a `POSTMORTEM` entry is the artifact that closes the loop |
| `PlatformStatusIncident` | `observability_platformstatusincident` | Operator-**curated** incident shown on `/status/` — deliberately distinct from `PlatformIncident` |
| `FrictionEvent` | `observability_frictionevent` | One `(user, school, view_name, kind, utc_day)` rollup — tenant-scoped via `school` FK |

The first five are declared in `monitoring.py` (alongside the health services) and
re-exported by `models.py` purely so Django registers them under this app label —
if you go looking for them in `models.py` you will only find imports.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `friction_digest_weekly` | Weekly friction digest to success owners |
| Module | `metrics` | 4-backend emit bridge; labels sanitized (sensitive values dropped, keys normalized, values truncated) |
| Module | `tracing` | The ONLY place `sentry_sdk` may be imported — `trace_view`, `start_named_transaction` |
| Module | `slo` + `slo_metrics` + `slo_clocks_service` | SLO SOT + `burn_rate` (≥1.0 = budget exhausts early; ≥14.4 = fast burn, page now) |
| Module | `incident_services` + `models_incident_timeline` | Idempotent incident upsert + timeline of record |
| Module | `sync_health` | Cross-rail collector for delta-sync / SODP / WAL (see below) |
| Module | `tenant_performance` | Tenant-facing trust dashboard — SLO **commitments only**, never fabricated live latency |
| Module | `public_status` / `tenant_public_status` | `/status/` HTML + JSON |
| Module | `logging_context` + `middleware` | ContextVar-based structured log fields + Prometheus request counters; also flags operator impersonation |
| Module | `telemetry_buffer` | Offline-safe buffer; drops PII keys on ingest |
| Module | `db_liveness` | Single place for the database liveness probe |
| Commands | `db_health_check`, `digest_friction`, `emit_prometheus_alert_rules`, `summarize_feedback_loop`, `synthetic_probe` | |

This app has **no `urls.py`** — its views (`views.py`, `views_metrics.py`,
`views_friction.py`) are routed from the config-level urlconfs.

## Before you change this

- **Never import `sentry_sdk` outside this app.** `scan_sentry_boundary.py` is a
  zero-baseline CI gate. Route through `apps.observability.tracing`.
- **The metrics backend must stay non-fatal.** `noop` is the default, and a missing
  `prometheus_client` / `statsd` library auto-falls back to structured-log with a
  one-time warning. A metric emission failure must never propagate into the caller's
  request path — observability that breaks the thing it observes is worse than none.
- **`PlatformIncident` and `PlatformStatusIncident` are two different things.** The
  first is the internal operational record; the second is what the public sees on
  `/status/` and is operator-curated. Do not merge them or auto-publish the first.
- **`tenant_performance` must never fabricate live latency.** It shows fleet
  availability, friction rollups, lifecycle milestones, and SLO *targets*. If you
  cannot measure it honestly for that tenant, do not show a number.
- **`telemetry_buffer` drops sensitive keys on ingest, not on flush.** Keep the
  redaction at the entry point — a packet author cannot block on the network, so the
  buffer is the last place the data is definitely still under our control.
- **`metrics._sanitize_labels` drops sensitive VALUES**, not just keys (regex over
  `password` / `secret` / `token` / `signature_text` / `private_key` / `email` / `slug`).
  Tenant slugs are hashed before emission elsewhere in the platform for the same
  reason — a metric label ends up in an operator dashboard and a third-party sink.
- **The Prometheus backend caches Counter/Gauge/Histogram per `(name, label_keys)`.**
  Without that, repeated emission trips "Duplicated timeseries". Don't construct
  collectors per call.
- `sync_health` exists because three offline rails failed into three stores with
  wildly different visibility — the WAL Redis review streams (`rmc.wal.deadletter.*`
  / `rmc.wal.conflict.*`) were **write-only with no reader anywhere** before it. If
  you add a fourth rail, add it here too or its failures are invisible.
- `slo.py` is the SOT and `verify_slo_registry.py` gates its shape: unique keys,
  `kind` in the allowed set, `target` in (0, 100), positive `window_days`, and
  `threshold_ms > 0` on latency kinds only.
