# RunMyCampus observability collector (T2 + T3)

An open-source, $0-vendor-lock-in metrics + alerting stack that pairs with the
platform's vendor-neutral telemetry bridge. Nothing here is required to run
RunMyCampus — it's an opt-in collector for operators who want Prometheus/Grafana.

## What's here

| File | Purpose |
|---|---|
| `docker-compose.yml` | Prometheus + Grafana, scraping the app's `/metrics/` (T3) |
| `prometheus.yml` | Scrape config + `rule_files` reference |
| `slo_alerts.yml` | **Generated** SLO-derived alerting rules (T2) |
| `grafana/provisioning/` | Auto-wires the Prometheus datasource |

## How the pieces connect

```
apps/observability/slo.py  ──emit──▶  slo_alerts.yml  ──load──▶  Prometheus rules
apps/observability/metrics.py (bridge) ──▶ /metrics/ ──scrape──▶ Prometheus ──▶ Grafana
```

* **SLOs are the source of truth.** `slo_alerts.yml` is generated from
  `apps/observability/slo.py`, so the alert config can't drift from the
  objectives. Regenerate after changing an SLO:

  ```
  python manage.py emit_prometheus_alert_rules > deploy/observability/slo_alerts.yml
  ```

* **The `/metrics/` endpoint is real but gated.** It's served only when the app
  runs with `OBSERVABILITY_METRICS_BACKEND=prometheus-client` (see
  `docs/OBSERVABILITY_METRICS.md`). Until then the `runmycampus-web` target shows
  **down** in Prometheus and the alert rules are **inert** — they reference
  metric series that don't exist yet, so they evaluate to nothing and never fire.
  This is deliberate: the objectives ship as code and light up as the
  instrumentation lands. Nothing here fabricates data.

## Metric naming contract

The generated alert rules expect these series (`<base>` = SLO key with `.`/`-`
normalised to `_`, namespaced `runmycampus_`):

| SLO kind | Expected series |
|---|---|
| availability / error_rate / freshness | `runmycampus_<base>_requests_total`, `runmycampus_<base>_failures_total` |
| latency_p95 / latency_p99 | `runmycampus_<base>_duration_seconds_bucket` (histogram) |

Wire the emit sites in `apps/observability/metrics.py` to match this convention
(or adjust the convention in `apps/observability/prometheus_alert_rules.py`) so
the alerts have data to evaluate.

## Run it

```
docker compose -f deploy/observability/docker-compose.yml up -d
# Prometheus  http://localhost:9090   (Status ▸ Rules to see the SLO alerts)
# Grafana     http://localhost:3000   (admin/admin; Prometheus datasource pre-wired)
```

**Operator runbook:** [`docs/PROMETHEUS_OPERATOR_DEPLOY_RUNBOOK.md`](../../docs/PROMETHEUS_OPERATOR_DEPLOY_RUNBOOK.md) — env vars, bearer auth, scrape target edits, live smoke (`verify_prometheus_stack_live.py`).

On Linux, `host.docker.internal` is mapped to the docker bridge gateway via
`extra_hosts`. If your app runs elsewhere, edit the `targets:` in
`prometheus.yml`.

## Alerting model

Multi-window burn-rate alerting per the Google SRE Workbook (the same thresholds
encoded in `apps/observability/slo.py::burn_rate_severity`):

* **page** — fast burn: error budget consumed at ≥14.4× over 1h.
* **ticket** — slow burn: ≥6× over 6h; latency SLOs alert when p95/p99 exceeds
  the objective for 10m.

Route the `severity` label to your pager/ticketing in Alertmanager (not bundled
here — operators wire their own notification channel).
