# OSS load testing (staging)

RunMyCampus does **not** require a paid load-testing SaaS. Use open-source tools against a **staging** stack:

| Layer | OSS default |
|-------|-------------|
| Database | PostgreSQL |
| Cache / broker | Redis |
| TLS edge | Caddy + Let's Encrypt (see `edge/README.md`) |
| DNS checks | dnspython (custom-domain wizard) |
| Load drivers | Locust (Apache 2.0) or k6 (AGPL) |

CI verifies harness **presence** only (`python scripts/verify_load_test_harness.py`) — not production-scale execution.

## Pre-flight (staging)

1. Migrate + seed operational wizard kernels:
   ```bash
   python manage.py migrate --noinput
   python manage.py seed_operational_wizard_kernels --all-active-schools
   ```
2. Point `DATABASE_URL` at Postgres and `CELERY_BROKER_URL` at Redis (attendance WAL + async paths).
3. Terminate TLS at Caddy; set `RMC_LOAD_HOST` to the tenant host (not bare localhost) when testing subdomain routing.
4. Mint a short-lived JWT for a teacher or admin test account → `RMC_LOAD_AUTH_TOKEN`.

## Locust (Apache 2.0)

```bash
pip install locust
export RMC_LOAD_AUTH_TOKEN="<jwt>"
export RMC_LOAD_SCHOOL_PATH="/t/demo-school"
locust -f scripts/load/locustfile_attendance_wal.py \
  --host=https://demo-school.staging.example.com \
  --users 500 --spawn-rate 50
```

For **50k concurrent** users, run distributed Locust workers (master + N workers) behind Caddy/nginx. Scale Postgres connection pool and Redis separately; watch `apps/observability` SLO panels during the run.

**Success criteria (operator-defined):** p95 attendance POST < 800 ms, error rate < 1%, no tenant isolation scanner regressions after the run.

## k6 (AGPL — smoke alternative)

```bash
export RMC_LOAD_HOST=https://demo-school.staging.example.com
export RMC_LOAD_AUTH_TOKEN="<jwt>"
k6 run scripts/load/k6_attendance_smoke.js
```

Use k6 for quick smoke before a full Locust soak.

## Evidence pack (optional)

Archive for release readiness:

- Locust/k6 stdout + HTML report
- Postgres `pg_stat_activity` peak connections
- Redis `INFO memory` snapshot
- Sentry issue count filtered by `school_id` during the window
