# Production infrastructure foundation (RunMyCampus on Render)

The platform's reliability rests on three open-source services. The application
code is already wired for all three and **degrades safely when any is absent** —
this doc is the operator runbook to provision them and the architecture rationale.

Open-source ≠ free hosting: PostgreSQL, Valkey (the BSD-licensed Redis fork), and
Celery are all free, auditable, and lock-in-free software. You pay only for the
compute that runs them. There is **no free always-on worker tier on Render**, so a
fully-async setup costs ~$20–25/mo — the cheapest path to ending the 502 loop.

## Why the crash-loop happened (root cause, 2026-06-17)

It was never RAM (memory sat at ~30%). It was **worker threads blocked on I/O**:
- **No Celery broker** → background tasks (provisioning, email, webhooks) ran
  *inline inside web requests*, blocking gthread worker threads.
- **DB-backed sessions** (`SESSION_ENGINE=db`) on **free, throttled Postgres** →
  every authenticated request read/wrote the session table.
- Threads filled → Render's 5s `/health/` probe got no thread → instance killed →
  reboot → repeat.

The fix is architectural, not a bigger box.

## The three services

| Service | Software | Render plan | Job |
|---|---|---|---|
| Database | PostgreSQL | **Basic+** (off free) | System of record. Free tier is throttled and expires at 30 days. |
| Key Value | **Valkey** (Redis-compatible) | Free works; **Starter** adds persistence | Cache + cache-sessions + Celery broker. |
| Worker | Celery (your code) | **Starter** (~$7/mo; no free worker tier) | Drains the task queue so background work leaves the web threads. |

## Provisioning (Render dashboard)

1. **Key Value (Valkey)** — New + → **Key Value** → **same region** as web + DB →
   plan (Free or Starter) → eviction policy **`allkeys-lru`** → Create. Copy its
   **Internal Connection URL** (private network — not internet-exposed).
2. **Wire it** — on **both** the web service and the worker service →
   Environment → set `REDIS_URL` **and** `CELERY_BROKER_URL` to that internal URL
   → Save. (The blueprint `render.yaml` already declares this wiring via
   `fromService`; setting it explicitly is the manual-service path.)
3. **Worker** — ensure the `school-management-system-worker` service is running
   (Starter). Without a running worker, queued tasks never drain.
4. **Postgres** — back up first, then Settings → Plan → upgrade off free.

## What the code already does (no action needed)

- `REDIS_URL` set → cache + sessions use Valkey; a slow/down Valkey **degrades to a
  clean miss** (django_redis `IGNORE_EXCEPTIONS` + `SOCKET_TIMEOUT`/
  `SOCKET_CONNECT_TIMEOUT`), never a hang.
- `CELERY_BROKER_URL` set → tasks enqueue to the broker; a web `.delay()` that hits
  a slow broker **fails fast** (bounded `CELERY_BROKER_TRANSPORT_OPTIONS` socket
  timeouts + one-retry publish policy), so it can never block a web thread.
- No broker configured → tasks fall back to inline (eager) execution so deferred
  work still runs (degraded, but functional).
- No `REDIS_URL` → cache stays in-process `LocMemCache` (zero DB load; intentionally
  not `DatabaseCache`, whose table would be missing in per-tenant schemas under
  django-tenants).

Tunable env (code defaults in `config/settings.py`, surfaced in `render.yaml`):
`REDIS_SOCKET_CONNECT_TIMEOUT` (2), `REDIS_SOCKET_TIMEOUT` (3),
`CELERY_BROKER_CONNECT_TIMEOUT` (2), `CELERY_BROKER_SOCKET_TIMEOUT` (4).

## Verify after provisioning

Visit `https://runmycampus.com/health/` — it reports the live wiring:
- `redis_configured: true`
- `cache_backend: django_redis.cache.RedisCache`
- `cache_socket_timeout: 3.0`
- `celery_broker_configured: true`
- `session_engine: …cache`

Then watch the web service Events tab — the "Instance failed: HTTP health check
timed out" entries should stop.

## Roadmap to scale (when paying tenants arrive)

- PgBouncer / connection pooling in front of Postgres.
- Larger Postgres plan + read replicas.
- Separate Celery queues (default / email / heavy) with per-queue worker counts.
- Persistent Valkey (Starter+) so queued tasks and sessions survive a restart.
