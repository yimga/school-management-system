# Observability

RunMyCampus observability stack — what's wired, how to wire what's missing, and
how to debug production incidents end-to-end.
Last reviewed: 2026-05-11.

---

## 1. What's wired today

| Layer | Tool | Status | Files |
|---|---|---|---|
| Application errors | Sentry (`sentry-sdk`) | Wired (DSN-gated) | `config/settings.py:1448-1464`, `apps/schools/middleware.py:SentryTenantTagMiddleware` |
| Request metrics | Prometheus (`prometheus_client`) | Wired | `apps/observability/middleware.py:ObservabilityMiddleware` |
| Structured logs | `python-json-logger` | Wired | log config in `config/settings.py` |
| Request correlation | Request-ID middleware | Wired | `apps/observability/middleware.py:RequestIdLoggingMiddleware` |
| Audit log | Custom middleware | Wired | `apps.compliance.middleware.AuditLoggingMiddleware` |
| Performance traces | Sentry traces (5% sample) | Wired | `SENTRY_TRACES_SAMPLE_RATE=0.05` |
| Profiling | Sentry profiles (0% sample) | Disabled by default | `SENTRY_PROFILES_SAMPLE_RATE=0.0` |
| Log shipping | OpenSearch DSN slot | Plumbed, not used | `OPENSEARCH_DSN` env in `settings_registry.py:329` |
| Real-user monitoring | — | **Missing** | — |
| Synthetic monitoring | — | **Missing** | — |
| APM dashboards | Sentry Performance only | Partial | — |
| Alerting | Sentry rules | Partial | — |
| SLO definitions | — | **Missing** | — |

Every Sentry event carries `school_id` (via `SentryTenantTagMiddleware`), `request_id`,
and `user_id` (when authenticated). Logs emit the same triple so log → Sentry pivot is
1-click in production.

## 2. Tags and correlation IDs

| Tag | Source | Cardinality | Usage |
|---|---|---|---|
| `school_id` | Tenant resolved from host or session | ~thousands | All errors, all logs |
| `request_id` | UUID4 minted per request | infinite | Stitch trace ↔ logs ↔ Sentry event |
| `user_id` | Authenticated `request.user.id` | ~hundreds-of-thousands | Logs, audit, Sentry user context |
| `endpoint` | Resolved URL name | ~hundreds | Prometheus labels, log filtering |
| `tenant_environment` | `production / staging / sandbox` | 3 | Sentry environment, Prom env label |

## 3. What metrics are collected

Auto-collected by `ObservabilityMiddleware` (Prometheus, scrapeable at `/metrics/` —
TODO confirm route is exposed):

- `http_requests_total{method, status, endpoint, school_id}` counter
- `http_request_duration_seconds{method, endpoint}` histogram
- `http_request_size_bytes`, `http_response_size_bytes`
- `db_query_duration_seconds` (if Django-DB instrumentation enabled)
- `db_query_count{endpoint}` for N+1 detection

Custom per-feature counters live in `apps/observability/metrics.py` and grow ad-hoc.

## 4. What's missing (priority order)

### Pass 6 — operational baseline

1. **Expose `/metrics/` on a separate port behind allowlist**. Currently the metrics endpoint may or may not be reachable from the Render runtime (verify). Production Prometheus scrapers need a stable endpoint.
2. **Sentry alert rules in code, not console.** Today rules are presumably set in the Sentry UI; commit `sentry/alerts.yml` and apply via Sentry CLI so they're reproducible.
3. **Service Worker error sink.** Service worker exceptions (sync queue failures, replay 4xx drops) currently log to `console.error` and disappear. Forward to Sentry-Browser via `static/js/service-worker.js` → `Sentry.captureException`.
4. **Celery instrumentation.** `sentry_sdk.integrations.celery.CeleryIntegration` exists but is not wired in the `sentry_sdk.init()` call at `settings.py:1457`. Add it. Without it, every background-task crash is invisible.
5. **Database slow-query log → Sentry.** Configure `LOGGING` to emit Django's slow-query handler at WARNING; Sentry captures WARNING+.
6. **Health endpoint** (`/healthz/`, `/readyz/`) — verify exists; if not, wire a dependency-aware version (Postgres ping + Redis ping + storage ping) for Render's health checks.

### Pass 7 — competitive parity

7. **Real-user monitoring (RUM)**: Sentry-Browser SDK on the frontend collecting page load times, web vitals (LCP, FID, CLS), JS error rates. Currently nothing tracks the parent dashboard taking 8 seconds to load on a 3G connection in rural India.
8. **Custom traces for business-critical flows**: Wrap attendance submit, grade entry, parent dashboard render in `sentry_sdk.start_transaction` so we can SLO them.
9. **SLOs in code**: Define `slo:availability >= 99.9%`, `slo:p95_latency <= 500ms` for top-10 endpoints. Generate burn-rate alerts.
10. **Log aggregation**: Ship structured logs to OpenSearch or Loki (the `OPENSEARCH_DSN` plumbing exists but no shipper is configured).
11. **Synthetic monitoring**: External uptime checker (Pingdom, Updown.io, or a self-hosted Blackbox Exporter) hitting the marketing landing, login, sample tenant dashboard, API health.
12. **Status page**: statuspage.io or self-hosted Cachet at `status.runmycampus.com` showing live + historical uptime per region.
13. **Cost telemetry**: Per-tenant Postgres connection use, per-tenant Sentry events, per-tenant AI Gateway requests — for fair-use enforcement and unit-economics analysis.

## 5. Runbook patterns

### "A specific tenant is seeing errors"

1. Sentry → filter by `school_id:<id>` → see the cluster.
2. Copy `request_id` from a representative event.
3. Render logs → `grep <request_id>` → see the full request lifecycle including DB calls.
4. If audit-related → query `AuditLog` for that request_id.

### "Latency spike across the platform"

1. Prometheus / Sentry Performance → which endpoint? which tenant?
2. If concentrated on one endpoint → check Sentry slow-query span data.
3. If concentrated on one tenant → check tenant size and recent imports.
4. Render dashboard → check Postgres connection saturation + Redis memory.

### "Background task silently dropped"

1. Verify Celery integration is wired in `sentry_sdk.init` (Pass 6 item 4).
2. Check `celery-flower` (if deployed) or `django-celery-results.TaskResult` for the task id.
3. Audit log: search for the trigger request_id.

## 6. SLO targets (proposed)

These are aspirational until the SLO-in-code work lands.

| Service | Availability | P95 latency | Burn-rate alert |
|---|---|---|---|
| Marketing site | 99.95% | 800 ms | 14-day burn × 1 hour |
| Login | 99.9% | 500 ms | 14-day burn × 1 hour |
| Parent dashboard | 99.5% | 1500 ms (cold), 600 ms (warm) | 14-day burn × 6 hours |
| Attendance submit | 99.5% | 1000 ms | 14-day burn × 6 hours |
| API write endpoints | 99.5% | 800 ms | 14-day burn × 6 hours |
| Background jobs (median) | 99% | 30 s | 30-day burn × 24 hours |

## 7. Cost guardrails

- **Sentry events**: per-tenant rate-limit at the SDK level (`before_send` filter) to prevent a single tenant's broken integration from burning the org's Sentry quota.
- **Prometheus cardinality**: keep `school_id` label opt-in for high-cardinality histograms.
- **Log volume**: structured logs to STDOUT; ship to OpenSearch with retention tiers (audit log: 1 year hot; access log: 90 days hot, 1 year cold).

## 8. Open questions

- Should we add OpenTelemetry instead of/alongside Sentry to give customers their own trace sinks (e.g. a district that wants traces in their Datadog)?
- Profiling sample rate: currently 0; consider 1% on production once we have a memory baseline.
- Mobile (PWA / Capacitor) telemetry: needs separate consideration after Pass 6 mobile work.
