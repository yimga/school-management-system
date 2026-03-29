# Section 25 — Observability and SRE

## Implemented

- **Structured logging / correlation:** `RequestIdLoggingMiddleware` sets `request.request_id`, `request.tenant_id`, `request.user_id` and passes them to `set_request_logging_context` (see `apps/observability/logging_context.py`). Response header `X-Request-ID` set. Use these in log formatters so every log line can include request_id/tenant_id. When **`LOG_JSON=1`** (or the project’s JSON logging toggle) is enabled, prefer a single JSON object per line: include at least **`request_id`**, **`tenant_id`**, **`user_id`**, and **`school_id`** when present (from `tenant_ctx` / verbose request formatting) so log aggregators can filter without regex.
- **Metrics:** `ObservabilityMiddleware` records Prometheus counters and histograms (`sms_http_requests_total`, `sms_http_request_latency_seconds`) by method, endpoint, status. Expose `/metrics` in production (behind auth or allowlist) for scraping.
- **Runbooks:** `docs/architecture/control_plane_runbooks.md` (and referenced in consolidated doc).

## SLOs and error budgets

- Define SLOs per surface (e.g. tenant API availability 99.9%, latency p99 < 2s). Document in this file or in a dedicated `slo_error_budgets.md`. Error budget = 1 - SLO; consume on violations; trigger review when exhausted.
- **Per-tenant SLOs (optional):** Metric labels already include no tenant in endpoint; for per-tenant SLOs, add tenant_id to metric labels where appropriate and define per-tenant targets.

## Synthetic monitoring

- **Health checks:** `/healthz/`, `/health/`, `/ready/` (see `apps/observability` and public/manager urlconfs). Use these for load balancer and synthetic probes.
- **Synthetic flows:** Add optional management command or scheduled job that hits key tenant and control-plane URLs and records success/latency (e.g. `python manage.py synthetic_probe --tenant=slug`). Document in runbooks.

## Tracing (optional)

- OpenTelemetry or Django middleware that creates a span per request and propagates trace_id. When implemented, add trace_id to logging context and document here.
