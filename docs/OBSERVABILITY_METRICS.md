# Observability metrics bridge

**Status:** shipped v3.39.0 (2026-05-19) — Migration Cloud wave Agent 4.
**SOT module:** [`apps/observability/metrics.py`](../apps/observability/metrics.py).
**Re-export:** [`services/observability.py`](../services/observability.py) (kept for the v3.38.0 Agent 4 introspection contract; new code should import from `apps.observability`).

**V3.40 boundary (Agent 5 ledger, 2026-05-19):** this document proves the v3.39 metrics bridge contract only. It may support the Migration Cloud V3.37-V3.40 evidence narrative, but it does not prove a production Prometheus/StatsD deployment, a public `/metrics/` firewall rule, or the future legacy webhook-header removal after **2026-08-18**.

## Why this exists

v3.38.0 Agent 4 shipped `apps/migration_cloud/metrics.py` with six typed `record_*()` helpers that introspect `services.observability` / `apps.observability.metrics` for `emit_counter` / `emit_gauge` callables and fall back to structured-JSON logging when neither is wired. The fallback works but every operator deployment paid the cost of running a log forwarder (Vector / Fluent Bit / Datadog) to reshape JSON lines into actual Prometheus / StatsD series. v3.39.0 ships the real bridge so deployments that already run Prometheus or StatsD can short-circuit the log forwarder and emit directly.

## Backend matrix

| Backend             | Production use case                                              | Library required               | Behavior on missing lib                                  |
|---------------------|------------------------------------------------------------------|--------------------------------|----------------------------------------------------------|
| `noop` (default)    | Dev / test / production deployments with no metric sink wired    | none                           | n/a — does nothing                                       |
| `structured-log`    | Deployments with a log forwarder already in place                | stdlib `logging`               | n/a — always available                                   |
| `prometheus-client` | Self-hosted Prometheus / Grafana stack; `/metrics/` pull model   | `prometheus_client` (optional) | falls back to `structured-log`; logs one-time WARNING    |
| `statsd`            | Datadog agent / push-model metric stack                          | `statsd` (optional)            | falls back to `structured-log`; logs one-time WARNING    |

## How to choose

* **Already running Datadog Agent on the host?** → `statsd` (zero infra change).
* **Already running Prometheus + Grafana?** → `prometheus-client` and configure a scrape job against `/metrics/` (firewalled — see security posture below).
* **Just want metrics out of the box without any infra?** → `structured-log` and let your existing log stack pick up the lines.
* **No metrics needed yet?** → leave the default `noop`.

## Settings

| Setting                                | Default        | Notes                                              |
|----------------------------------------|----------------|----------------------------------------------------|
| `OBSERVABILITY_METRICS_BACKEND`        | `"noop"`       | one of `noop` / `structured-log` / `prometheus-client` / `statsd` |
| `OBSERVABILITY_METRICS_STATSD_HOST`    | `""`           | StatsD UDP host (falls back to `"localhost"`)      |
| `OBSERVABILITY_METRICS_STATSD_PORT`    | `8125`         | StatsD UDP port                                    |
| `OBSERVABILITY_PROMETHEUS_NAMESPACE`   | `"runmycampus"`| Prepended to every Prometheus metric name          |

All four are environment-driven (`os.getenv(...)`) so per-environment override is just an env var.

## Public API

```python
from apps.observability import emit_counter, emit_gauge, emit_histogram

emit_counter("migration_cloud.companion_uploads.count", labels={"scheme": "x25519"})
emit_gauge("migration_cloud.companion_uploads.bytes_total", 32_768.0, labels={"tenant_id": "abc123"})
emit_histogram("api.request_duration_ms", 47.2, labels={"endpoint": "bundles"})
```

`emit_counter` accepts both `labels=` (canonical) and `tags=` (legacy v3.38 Agent 4 kwarg). Both call sites work identically.

## Label discipline (sanitization rules)

Every emission runs through `_sanitize_labels(labels)`. Three transforms in order:

1. **Sensitive-value drop.** Any label whose VALUE contains a keyword from the sensitive list (`password` / `passwd` / `pwd` / `secret` / `token` / `signature_text` / `private_key` / `email` / `slug` / `ssn` / `dob` / `api_key` / `apikey`) is dropped entirely. The keyword list mirrors `scripts/scan_pii_logging_smell.py` so the scanner-enforced "do not log PII" contract extends to metric labels.
2. **Value truncation.** Values longer than 64 chars are truncated. Prometheus best-practice — long labels cardinality-explode dashboards.
3. **Key normalization.** Keys are lowercased; any character outside `[a-z0-9_]` becomes `_`; if the resulting key starts with a digit, `_` is prepended. Conforms to Prometheus's `[a-z_][a-z0-9_]*` label-name rule.

Tenant identifiers MUST be hashed BEFORE landing here. Migration Cloud's `apps/migration_cloud/metrics.py::_hash_tenant_id` returns `sha256(slug)[:12]` and is the source of truth — never label-emit a plaintext slug.

## `/metrics/` endpoint security posture

When `OBSERVABILITY_METRICS_BACKEND == "prometheus-client"`, `config/urls.py` lazy-includes `PrometheusMetricsView` at `/metrics/`. Three boundary properties hold:

1. **Anonymous-readable.** No auth header is required — Prometheus scrape jobs are configured at infra time and shouldn't bake credentials into a scrape config.
2. **Firewalled at infra.** Production deploys MUST restrict `/metrics/` to the Prometheus scrape subnet via a network ACL or sidecar (e.g. nginx `allow 10.0.0.0/8; deny all;`). The wider internet must NEVER reach this endpoint.
3. **No plaintext PII in labels.** Tenant slugs are pre-hashed by Migration Cloud; the sanitizer drops anything else that looks PII-shaped. An operations team member viewing `/metrics/` sees series like `runmycampus_migration_cloud_companion_uploads_count{tenant_id="a3f2c8b1d09e",scheme="x25519"}` — never `tenant_id="acme-prep-academy"`.

The view carries `# rbac-allow: prometheus-scrape-anonymous-firewall-protected` so the role-permission audit (`audit_role_permission_matrix.py`) doesn't flag it as missing auth.

## Operator deploy snippets

**Full runbook:** [`docs/PROMETHEUS_OPERATOR_DEPLOY_RUNBOOK.md`](PROMETHEUS_OPERATOR_DEPLOY_RUNBOOK.md) (compose, Grafana, live smoke).

### Prometheus scrape config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'runmycampus'
    scrape_interval: 30s
    static_configs:
      - targets: ['runmycampus-internal.svc.cluster.local:8000']
    metrics_path: /metrics/
```

Set `OBSERVABILITY_METRICS_BACKEND=prometheus-client` on the Django pod env.

### StatsD agent config (Datadog example)

```yaml
# datadog.yaml
use_dogstatsd: true
dogstatsd_port: 8125
dogstatsd_non_local_traffic: true
```

Set on the Django pod env:

```
OBSERVABILITY_METRICS_BACKEND=statsd
OBSERVABILITY_METRICS_STATSD_HOST=datadog-agent.svc.cluster.local
OBSERVABILITY_METRICS_STATSD_PORT=8125
```

### Structured-log shipper config (Vector example)

```toml
[sources.django_logs]
type = "kubernetes_logs"

[transforms.observability_metrics]
type = "filter"
inputs = ["django_logs"]
condition = '.message contains "observability_metric "'

[sinks.prometheus_rw]
type = "prometheus_remote_write"
inputs = ["observability_metrics"]
endpoint = "https://prometheus.svc.cluster.local/api/v1/write"
```

Set `OBSERVABILITY_METRICS_BACKEND=structured-log`. Every emission appears on `logging.getLogger("observability.metrics")` at INFO with payload `observability_metric {JSON}`.

## Backwards compatibility with v3.38.0 Agent 4

`apps/migration_cloud/metrics.py::_resolve_backend()` introspects two module paths in order:

1. `services.observability`
2. `apps.observability.metrics`

Both now export `emit_counter` / `emit_gauge` and resolve to the same backend dispatch. v3.38 Agent 4 callers pass `tags=` (legacy kwarg); v3.39 accepts both `tags=` and `labels=`. Zero changes required in `apps/migration_cloud/metrics.py` — the introspection path still finds the callable, and the new dispatch routes it to the configured backend instead of falling back to structured logging on every call.

## Honest deferrals

* Histogram buckets are currently library-default (prometheus_client default; statsd timing) — per-metric custom buckets not yet supported.
* No `/metrics/` Bearer-token auth option — relies on infra-layer firewalling. Add when a deployment needs internet-exposed scraping (rare).
* No distinct "scrape token" header — Prometheus scrape config doesn't need one when network-firewalled.
