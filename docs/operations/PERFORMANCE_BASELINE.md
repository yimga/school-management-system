# Performance baseline — load + perf budgets

This is the contract any deployment must meet before it is declared "live".
Two layers: synthetic Lighthouse budgets per page (already enforced by
`lighthouserc.cjs`) and macro load budgets via k6.

## 1. Per-page synthetic budgets (Lighthouse)

Defined in `lighthouserc.cjs`. CI gate via `.github/workflows/lighthouse-ci.yml`.

| Metric | Loose target | Strict target (`LHCI_STRICT_N10=1`) |
|---|---|---|
| Performance score | ≥ 0.75 | ≥ 0.82 |
| LCP | ≤ 4000 ms | ≤ 3500 ms |
| CLS | ≤ 0.15 | ≤ 0.15 |
| TBT | ≤ 300 ms | ≤ 300 ms |
| Total JS (gzipped) | ≤ 250 KB | ≤ 250 KB |
| Total CSS (gzipped) | ≤ 100 KB | ≤ 100 KB |

## 2. Macro load budgets (k6)

Defined in `tests/load/k6_baseline.js`. The default profile is **6 virtual
users for 5 minutes** hitting the homepage + `/-/version/` + `/health/`.

| Metric | Threshold |
|---|---|
| `http_req_failed` | < 1% |
| `http_req_duration` p95 | < 1500 ms |
| `errors` (custom counter) | < 5 over the run |

Soak profile (`VUS=10 DURATION=30m k6 run tests/load/k6_baseline.js`) is
intended for staging — it is not yet a CI gate because we have no staging
environment dedicated to load runs.

### Running locally

```bash
# Start the dev server in another terminal first:
python manage.py runserver 127.0.0.1:8000

# Default profile (6 VUs, 5 min)
BASE_URL=http://127.0.0.1:8000 k6 run tests/load/k6_baseline.js

# Heavier soak (10 VUs, 30 min)
BASE_URL=http://127.0.0.1:8000 VUS=10 DURATION=30m k6 run tests/load/k6_baseline.js
```

### Running against staging

```bash
BASE_URL=https://manager.runmycampus.com k6 run tests/load/k6_baseline.js
```

The script exits non-zero if any threshold is breached, so it can be wired
into a deploy pipeline.

## 3. SLO targets (production)

Aligned with `docs/operations/SLA.md`:

- **Authenticated availability**: 99.5% / month
- **Public marketing availability**: 99.0% / month
- **API p95 latency** (read endpoints): < 800 ms
- **API p95 latency** (write endpoints): < 1500 ms
- **Webhook delivery success rate** (per provider): > 99% over 24h

These cannot be measured from inside the repo — they need a deployed
environment + an APM like Sentry / Datadog wired to `apps/observability/`.

## 4. Recorded k6 runs (repo artifact)

When a baseline completes, `scripts/run_k6_baseline_local.sh` (or CI
`k6-baseline-dispatch.yml`) writes **`docs/generated/k6_baseline_last_run.json`**
via `scripts/record_k6_baseline_results.py`. Status is `recorded` when k6 ran;
`pending` until the first successful export. Dispatch workflow or local:

```bash
bash scripts/run_k6_baseline_local.sh
# or: gh workflow run k6-baseline-dispatch.yml
```

## 5. Capacity headroom

When k6 + Lighthouse both pass, the deployment is considered ready. When a
threshold breaches:

1. Identify the slow endpoint via the `endpoint` tag in the k6 output.
2. Check `docs/generated/raw_sql_audit.md` for N+1 hotspots in that area.
3. Re-run `python scripts/audit_query_hotspots.py` for the affected app.
4. Add an index, fix the query, or batch the call.
5. Re-run k6; commit the fix when it passes.

## 6. What this doc does NOT cover

- DR / RTO / RPO — see `docs/DR_BACKUP_RESTORE_RUNBOOK.md`.
- Provider-side SLOs (Stripe, Render, etc.) — those are the providers' contracts.
- Cost per request — out of scope here.
