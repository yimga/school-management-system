# Scheduling without a Celery worker

Production runs **web + Valkey + Postgres, no Celery worker** (cost-minimal; see
`render.yaml`). With `CELERY_BROKER_URL` unset, Celery runs **eager** (tasks
execute inline in the request) and there is **no beat process**, so the ~90
`CELERY_BEAT_SCHEDULE` entries never fire on their own.

This document describes how scheduled work runs anyway, and how to add a real
worker later **without disruption**.

## The one registry, three triggers

All three mechanisms converge on a single registry —
[`apps/platform_runtime/periodic.py`](../apps/platform_runtime/periodic.py) — and
the **same per-job locking**, so no trigger can double-fire a job.

| # | Mechanism | For | Runs in | Cost |
|---|-----------|-----|---------|------|
| 1 | In-process tick off `/health/` | light, idempotent, periodic jobs | a web-dyno background thread | free |
| 2 | Secured endpoint `/api/internal/cron/run/` + free external scheduler | any job, incl. heavier | the web process (or background thread) | free (GitHub Actions) |
| 3 | `manage.py run_periodic_jobs` via Render `cron` | heavier jobs needing their own process | a short-lived cron container | paid (per-run) |

### 1. In-process tick (the default)

The constantly-pinged `/health/` view calls `maybe_run_due_jobs()`. That call is
**pure-memory and non-blocking**: it does a monotonic throttle check on the
request thread and, at most once per `RMC_PERIODIC_SCAN_THROTTLE` seconds
(default 60) per process, hands **all** cache I/O + job execution to a daemon
thread. The health probe is never delayed by cache or job runtime — a blocking
probe is exactly the 502 crash-loop we already fixed.

Cross-worker safety: a job claims a shared `cache.add()` lock (Valkey-backed in
prod) and stamps a shared `last_run` timestamp, so only one thread across all
workers runs it per interval.

**Only light, idempotent jobs belong here** — they share the web dyno's threads.

### 2. Secured endpoint + free external scheduler

`POST /api/internal/cron/run/`, authed by the `INTERNAL_CRON_TOKEN` shared secret
(constant-time compared; endpoint returns 404 when the token is unset/short).

- Body `{}` → run all **due** jobs. `{"job":"<name>"}` → one job.
  `{"force":true}` → run even if not due. `{"background":true}` → 202 + run in a
  thread (for long jobs).
- `GET` the same URL → registry status (intervals, last run, due-now) for
  monitoring.

The **free** scheduler is [`.github/workflows/cron-trigger.yml`](../.github/workflows/cron-trigger.yml)
— a GitHub Actions cron that hits the endpoint every 15 min. Set repo secrets
`RMC_CRON_URL` and `INTERNAL_CRON_TOKEN`. (cron-job.org / UptimeRobot work too.)

### 3. Render cron (own process, for heavy jobs)

A commented-out `type: cron` block in `render.yaml` runs
`manage.py run_periodic_jobs` on a schedule in its **own** container — so heavy
jobs don't touch the web dyno's threads. Billed per-run; uncomment to enable.

Run it by hand anytime:

```bash
python manage.py run_periodic_jobs            # run all due
python manage.py run_periodic_jobs --force    # run all now
python manage.py run_periodic_jobs --job customersuccess.recompute_benchmark_cohorts --force
python manage.py run_periodic_jobs --list     # schedule state, run nothing
```

## Adding a job

In `apps/platform_runtime/periodic.py`, register inside `ensure_default_jobs()`:

```python
register_job(
    "myapp.my_job",
    interval_seconds=WEEKLY_SECONDS,        # or any int
    func=_run_my_job,                       # zero-arg callable; delegate to a
                                            # management command / service so the
                                            # future worker path runs the same code
    description="What it does.",
    tags=("light",),                        # tag "light" if safe for the /health/ tick
)
```

Keep in-process jobs light + idempotent. Route heavy/tenant-fan-out work through
Option 2/3 (their own process), or a real worker (below).

## Future: adding a real Celery worker (no disruption)

Nothing here blocks moving to a proper worker + beat later, and the handoff is
automatic:

1. Each registered job delegates to the **same** callable its `@shared_task`
   wraps (e.g. the `recompute_benchmark_cohorts` management command), so there is
   **no duplicate logic** to reconcile.
2. `inprocess_scheduler_enabled()` defaults to `auto` = enabled **only while
   `CELERY_BROKER_URL` is unset**. The moment you provision a broker + worker +
   beat (uncomment the worker/beat blocks in `render.yaml` and re-add the web
   broker), the in-process tick **stands down by itself** — no code change, no
   double execution. Override with `RMC_INPROCESS_SCHEDULER=on|off` if you ever
   want both or neither.
3. The secured endpoint and `run_periodic_jobs` keep working as manual/triggered
   escape hatches regardless.

So the migration is: enable the worker → in-process scheduler auto-disables →
beat drives the schedule. The endpoint and command remain as on-demand triggers.
