# Prometheus operator deploy runbook

**Status:** batch 1721 (2026-06-24) — pairs with the in-repo collector at `deploy/observability/` and the metrics bridge in `apps/observability/metrics.py`.

This stack is **opt-in**. RunMyCampus runs fine without it. Use it when you already run Prometheus/Grafana and want SLO burn-rate alerts on the same series the app emits.

## Architecture

```
Django (prometheus-client backend)
  └── GET /metrics/  ←── scrape ── Prometheus (:9090)
                              └── rules ← slo_alerts.yml (generated from slo.py)
                              └── Grafana (:3000)
```

| Artifact | Role |
|---|---|
| `deploy/observability/docker-compose.yml` | Prometheus + Grafana |
| `deploy/observability/prometheus.yml` | Scrape job `runmycampus-web` → `/metrics/` |
| `deploy/observability/slo_alerts.yml` | **Generated** alert rules — do not hand-edit |
| `apps/observability/slo_metrics.py` | Emit sites wired to SLO keys |
| `docs/OBSERVABILITY_METRICS.md` | Backend selector + label discipline |

## Prerequisites

1. **Python dependency:** `prometheus_client` installed in the app environment.
2. **Backend env:** `OBSERVABILITY_METRICS_BACKEND=prometheus-client`
3. **Optional auth:** `OBSERVABILITY_METRICS_BEARER_TOKEN=<secret>` — when set, `/metrics/` requires `Authorization: Bearer <token>` (configure the same token in `prometheus.yml` `bearer_token` under the scrape job).
4. **Network:** Prometheus must reach the app host/port. Default scrape target is `host.docker.internal:10000` (see `prometheus.yml`).

## Step 1 — Enable the metrics endpoint

```bash
export OBSERVABILITY_METRICS_BACKEND=prometheus-client
export OBSERVABILITY_PROMETHEUS_NAMESPACE=runmycampus
# optional:
# export OBSERVABILITY_METRICS_BEARER_TOKEN="$(openssl rand -hex 32)"

python manage.py runserver 0.0.0.0:10000
```

Verify locally:

```bash
curl -sS http://127.0.0.1:10000/metrics/ | head
# expect lines like: runmycampus_web_availability_requests_total{...}
```

If you see **404**, the backend is not `prometheus-client` or `prometheus_client` is not installed.

## Step 2 — Regenerate alert rules (after SLO changes)

```bash
python manage.py emit_prometheus_alert_rules > deploy/observability/slo_alerts.yml
python scripts/verify_prometheus_observability_stack.py
```

CI runs the drift compare on every PR — committed `slo_alerts.yml` must match `slo.py`.

## Step 3 — Start the collector

From the repo root (`beta/school-management-system/`):

```bash
docker compose -f deploy/observability/docker-compose.yml up -d
```

| Service | URL | Default credentials |
|---|---|---|
| Prometheus | http://localhost:9090 | none |
| Grafana | http://localhost:3000 | `admin` / `admin` (override via `GRAFANA_ADMIN_*`) |

**Linux:** `host.docker.internal` is mapped via `extra_hosts` in compose. If the app listens on another port, edit `deploy/observability/prometheus.yml` `targets:` or set `RMC_METRICS_TARGET=host:port` and templatize the file in your deploy layer.

**Production:** firewall `/metrics/` to the Prometheus scrape subnet only. Anonymous scrape is allowed by design when no bearer token is set — see `docs/OBSERVABILITY_METRICS.md` § `/metrics/` endpoint security posture.

## Step 4 — Confirm scrape + rules

1. Prometheus → **Status → Targets** — `runmycampus-web` should be **UP** (requires Step 1).
2. Prometheus → **Status → Rules** — SLO groups from `slo_alerts.yml` loaded.
3. Prometheus → **Graph** — query `runmycampus_web_availability_requests_total` after traffic hits the app.

Alerts stay **inert** until matching series exist — that is expected on a fresh deploy.

## Step 5 — Operator smoke script

```bash
python scripts/verify_prometheus_observability_stack.py   # static / drift gate (CI)
python scripts/verify_prometheus_stack_live.py            # soft pass if stack down
python scripts/verify_prometheus_stack_live.py --strict   # fail unless live
```

Environment overrides:

| Variable | Default | Purpose |
|---|---|---|
| `RMC_METRICS_URL` | `http://127.0.0.1:10000/metrics/` | App scrape probe |
| `RMC_PROMETHEUS_URL` | `http://127.0.0.1:9090/-/healthy` | Collector health |
| `RMC_PROMETHEUS_PROBE_TIMEOUT` | `4` | HTTP timeout seconds |

npm: `npm run verify:prometheus-stack-live`

Pass `--check-django` (or set `OBSERVABILITY_METRICS_BACKEND` in the environment) when you need Django settings loaded; default skips Django for a fast operator probe.

## Grafana

Datasource provisioning ships at `deploy/observability/grafana/provisioning/datasources/prometheus.yml` (Prometheus at `http://prometheus:9090` inside the compose network). Build dashboards against `runmycampus_*` series; route `severity=page` / `severity=ticket` labels to your pager when you add Alertmanager.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Target **down** | App not on `prometheus-client` or wrong port | Step 1 + fix `prometheus.yml` target |
| `/metrics/` 401 | Bearer token set | Add `bearer_token` to scrape config or unset token in dev |
| Rules loaded, no alerts | No traffic / no emit yet | Generate requests; check `verify_slo_metrics_emit_sites.py` |
| `slo_alerts.yml` CI fail | Drift from `slo.py` | Regenerate (Step 2) |
| `docker compose config` fail | Docker not installed or bad YAML | Install Docker; run static verifier only |

## Related verifiers

- `verify_prometheus_observability_stack.py` → **PROMETHEUS_OBSERVABILITY_STACK_PASS** (CI)
- `verify_slo_metrics_emit_sites.py` → **SLO_METRICS_EMIT_SITES_PASS**
- `verify_prometheus_stack_live.py` → **PROMETHEUS_STACK_LIVE_PASS** / **SOFT_PASS** (operator)
