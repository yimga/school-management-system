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

**This endpoint is the ONLY trigger for the 26 `auto_eligible=False` jobs.** The
`/health/` tick deliberately runs `auto_only=True`, so heavy / financial /
tenant-fan-out work never touches the request-serving thread. Measured by running
`registry_status()` on 2026-09-02: **34 registered, 8 auto-eligible, 26 cron-only.**

#### Verified contract

Every row below was verified by executing the route, not by reading it; the
assertions live in
`apps/platform_runtime/tests/test_cron_trigger_reachability_2026_09_02.py`.

| Property | Value |
|---|---|
| Path | `/api/internal/cron/run/` |
| Methods | `GET` (status, read-only) and `POST` (run). Anything else -> **405** |
| Auth header | `Authorization: Bearer <secret>` — also accepts `Authorization: Token <secret>`, a bare `Authorization: <secret>`, the header `X-Cron-Key: <secret>`, or `{"token": "..."}` in the POST body |
| Secret | `INTERNAL_CRON_TOKEN`, **minimum 16 characters** (`MIN_TOKEN_LEN`), constant-time compared |
| Token unset or < 16 chars | **404** — deliberately indistinguishable from "no such URL" |
| Missing / wrong token | **403** |
| Rate limit | **30 requests / 60s per client IP**, then **429** (fails open if the cache is down) |
| Body > 4096 bytes | **413**. Malformed JSON -> **400** |
| `POST {}` | run every **due** job, synchronously -> **200** `{"status":"ok","results":[...]}` |
| `POST {"job":"<name>"}` | run just that job |
| `POST {"force":true}` | run even if not due (also **rebases** the schedule) |
| `POST {"background":true}` | **202** `{"status":"accepted"}` — returned **before any job starts** |
| `GET` | **200** `{"jobs":[...], "evidence":[...], "summary":{...}}` |

#### Which hosts serve it

`UrlConfSwitcherMiddleware` picks the urlconf from the `Host` header, and the
route is now mounted from one shared list (`config/internal_machine_urls.py`) that
**every** deployment-served urlconf splats — `config.urls`, `config.manager_urls`,
`config.public_urls`, `config.tenant_urls`, `config.api_urls`.

> Before 2026-09-02 it was declared inline in `config/urls.py` and
> `config/manager_urls.py` only. Every sovereign box routes to
> `config.tenant_urls`, so on a box this endpoint returned **404 — and 404 is also
> what an unset token returns**, so the outage read as a missing secret and was
> never diagnosed. If you are hitting a revision older than this fix, use the
> **manager** host, or use `manage.py run_periodic_jobs` (below), which never
> depended on the URL layer.

#### Runbook — CLOUD (Render)

The token is minted by Render (`generateValue: true` in `render.yaml`); read it
from the service's Environment tab. **Fill in line 1, then paste the rest as one
block.**

```bash
CRON_HOST=https://manager.runmycampus.com
```

```bash
# Prompts for the secret; it is not echoed and never enters shell history.
read -rsp 'INTERNAL_CRON_TOKEN: ' CRON_TOKEN; echo
CRON_URL="$CRON_HOST/api/internal/cron/run/"

# BEFORE — durable evidence. Read-only: no jobs run, no recovery threads spawned.
curl -sS -H "Authorization: Bearer $CRON_TOKEN" "$CRON_URL" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["summary"])'

# TRIGGER — every due job, in a background thread (202 returns immediately).
curl -sS -i -X POST -H "Authorization: Bearer $CRON_TOKEN" \
  -H 'Content-Type: application/json' -d '{"background": true}' "$CRON_URL"

# AFTER — re-read the evidence. cron_only_never_invoked must fall to 0.
curl -sS -H "Authorization: Bearer $CRON_TOKEN" "$CRON_URL" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["summary"])'
```

A **manual one-shot** needs no token at all — run it in the Render Shell:

```bash
python manage.py run_periodic_jobs
python manage.py report_scheduled_job_evidence --cron-only
```

For the **recurring** trigger, point a free pinger (cron-job.org / UptimeRobot) at
`$CRON_URL` with the `Authorization: Bearer` header and body `{"background":true}`
every 5 minutes. Stay under 30 requests/minute per source IP or it 429s.

#### Runbook — BOX (self-host Docker Compose)

`RMC_DIR` is the directory holding `docker-compose.yml` on that box; this file
cannot know it, so set it yourself on line 1, then paste the rest as one block.

```bash
RMC_DIR=
```

```bash
cd "${RMC_DIR:?fill in the RMC_DIR= line above before pasting this block}" || exit 1

# BEFORE
docker compose exec -T web python manage.py report_scheduled_job_evidence --cron-only

# TRIGGER — the complete beat-less rail, in the web container.
docker compose exec -T web python manage.py run_periodic_jobs

# AFTER — non-zero exit if any job did not succeed in the last 15 minutes.
docker compose exec -T web python manage.py report_scheduled_job_evidence \
  --cron-only --fail-unless-succeeded-within 900
```

Make it recurring. Still inside that directory, run this to PRINT the exact
crontab line with the real path already substituted, then paste its output into
`crontab -e`:

```bash
echo "*/5 * * * * cd $PWD && docker compose exec -T web python manage.py run_periodic_jobs >> /var/log/rmc-periodic.log 2>&1"
```

#### Proving it ran

A 200 does not mean a job ran, and a 202 is returned *before* any job starts. The
cache-based `jobs` block cannot help either: `periodic._claim()` writes `last_run`
**before** calling the job, so a job that raised on its first statement still
reports a fresh `last_run_epoch` and `due_now: false`, and the cache is wiped on
every deploy.

Use the durable evidence instead — `ScheduledJobHeartbeat` joined against the
registry, so **every registered job gets a row even when it has never run** (the
Django admin lists heartbeat rows, which is why 26 never-run jobs were invisible
there):

```bash
python manage.py report_scheduled_job_evidence                    # all jobs
python manage.py report_scheduled_job_evidence --cron-only        # the 26
python manage.py report_scheduled_job_evidence --json             # machine-readable
python manage.py report_scheduled_job_evidence --fail-on-never-invoked
python manage.py report_scheduled_job_evidence --fail-unless-succeeded-within 900
```

Verdicts: `ok` | `stale` (succeeded, but too long ago) | `failing` (invoked, never
succeeded — read `last_error`) | `never_invoked` (**nothing triggers it on this
deployment**). The last two are different diagnoses that the older
`monitor_scheduled_job_health` reports identically, because both have
`last_success_at IS NULL`.

`report_scheduled_job_evidence` is strictly read-only — unlike
`monitor_scheduled_job_health`, which spawns auto-recovery threads for stale jobs
and so cannot be used as an unbiased "did the trigger work?" check.

The **free, zero-infra** path is a third-party pinger (cron-job.org / UptimeRobot)
that POSTs this endpoint with the `INTERNAL_CRON_TOKEN` Bearer header on a schedule
— zero GitHub Actions minutes. (A `.github/workflows/cron-trigger.yml` GitHub
Actions cron previously did this but was **removed**: GitHub bills Actions per job
rounded up to the minute, so the tick overran the free 2,000-min/mo tier and made
scheduled jobs silently go dark. The in-process scheduler above already covers
light jobs without any external tick.)

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
