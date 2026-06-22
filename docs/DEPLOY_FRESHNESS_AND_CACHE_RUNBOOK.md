# Deploy freshness & cache runbook

> "I pushed to `main` but I don't see the change." This doc tells you, in under a
> minute, **which** of the two independent caches is responsible and exactly how
> to clear it. They are different layers — diagnosing the wrong one wastes days.

## The one mental model

A change has to clear **two** gates to become visible:

```
  your push ──▶ [Gate 1: the DEPLOY]  ──▶ server runs new code
                                           │
  your browser ◀── [Gate 2: the BROWSER] ◀─┘   (service-worker cache)
```

- **Gate 1 — the deploy (server side).** Render must build the new commit and
  start serving it. If it doesn't, the *server itself* is running old code.
- **Gate 2 — the browser (client side).** A **service worker** installed in your
  browser can answer page loads from its own on-device cache. A stale one serves
  old HTML even when the server is brand new. **A hard refresh does NOT fix this.**

> These are unrelated. Server-side **Valkey/Redis** is NOT either gate — it caches
> data + login sessions, never rendered pages. Clearing it changes nothing here.

## 30-second diagnosis: which gate is stuck?

1. **Check what's actually live (server truth, browser-independent):**
   open `https://new-school.runmycampus.com/health/` and read `render_git_commit`.
   Compare it to the latest commit on `main` (`git log origin/main -1`).
   - **It lags `main`** → **Gate 1 (deploy)** is the problem. Go to §A.
   - **It matches `main`** → the server is fresh; the staleness is in your browser.
     Go to §B.

2. **Confirm the browser (client truth):** open the tenant in an **Incognito /
   Private window** (Ctrl+Shift+N). Incognito has no service worker.
   - **Incognito looks correct, normal window doesn't** → **Gate 2 (browser)**. §B.

## §A — Fix Gate 1: the deploy isn't landing

Deploys are **Render-native** (Render → GitHub integration). GitHub Actions does
**not** deploy this app, so Actions minutes / the cron workflow are irrelevant here.

Causes, in priority order:

1. **Auto-Deploy is OFF.** This is the #1 cause of "commits sit for days." If
   Auto-Deploy is off, a push to `main` does nothing until someone clicks Manual
   Deploy. **Fix:** Render → the `school-management-system` web service →
   **Settings → Build & Deploy → Auto-Deploy → On.** Safe to leave on now that
   predeploy migrations are idempotent (see #2).
2. **A predeploy migration crashed the build.** The predeploy
   (`scripts/release/render_predeploy.sh`, `migrate_schemas --shared` then
   `--tenant`) runs under `set -e`; if a migration raises, Render **aborts the
   deploy and keeps serving the old image.** Fix pattern: make the migration
   idempotent (`SeparateDatabaseAndState` + a `RunPython` heal that creates only
   what's missing — see migrations `0092`, finance `0072`). Verify drift is clean:
   `python manage.py heal_tenant_schema_drift` (dry-run) on the Render shell.
3. **Deploy thrash.** Many rapid pushes cancel in-flight builds. With Auto-Deploy
   on and idempotent migrations this self-heals; if you're pushing in a tight
   burst, give the last push a few minutes to build.

**Where to see the truth:** Render → **Events** → click the latest deploy to read
its full log (the runtime *Logs* tab only shows the predeploy at the deploy
minute). The browser-independent check is always `/health/` `render_git_commit`.

## §B — Fix Gate 2: a stuck service worker in the browser

The deployed worker is self-updating: `/sw.js` is served `no-cache` with full-site
scope, uses **network-first for HTML**, and calls `skipWaiting()` + `clients.claim()`
so **new visitors always get fresh content.** Only a browser that registered an
**older, cache-first** worker (before those fixes) stays stuck.

Three ways to clear a stuck worker:

1. **One-click (anyone):** visit `https://<host>/sw-reset/`. It unregisters every
   service worker for the origin, deletes every cache bucket, and reloads. Now
   routed on tenant, public, and manager hosts.
2. **DevTools (you, now):** F12 → **Application** → **Storage** → **Clear site
   data** → reload.
3. **Just test in Incognito** — no worker there, always the true server state.

Why a hard refresh doesn't work: it bypasses the worker for *one* request but
never unregisters it, so the next navigation is stale again.

## Scheduled jobs (separate system — not deploys)

Background periodic jobs (benchmark recompute, sweeps, alerts) are driven by an
**in-process scheduler** — "Celery beat without a worker" — that ticks off the
constantly-pinged `/health/` probe (`RMC_INPROCESS_SCHEDULER=auto`,
`apps/.../periodic.py`). This is the app's **original**, self-contained mechanism
and is always on in the web-only topology (`/health/` shows
`inprocess_scheduler: true`).

The GitHub Actions cron (`.github/workflows/cron-trigger.yml`) that used to POST
`/api/internal/cron/run/` as a backup tick was **removed** — GitHub bills Actions
per job rounded up to the minute, so the tick overran the free 2,000-min/mo tier
and made scheduled jobs silently go dark. The in-process scheduler above is now the
sole driver and covers light jobs. It never deployed anything, so removing it has
no effect on deploy freshness. If you ever need a guaranteed external tick (for
heavy jobs), point a free third-party pinger (cron-job.org / UptimeRobot) at
`POST /api/internal/cron/run/` with the `INTERNAL_CRON_TOKEN` Bearer header — zero
GitHub minutes, never throttled. The secured endpoint itself is unchanged.

## Quick reference

| Symptom | Check | Fix |
|---|---|---|
| Pushed, not live | `/health/` `render_git_commit` lags `main` | Auto-Deploy On; or Manual Deploy latest; check Render Events for a failed predeploy |
| Live commit correct, page still old | Incognito looks right | `/sw-reset/` or DevTools → Clear site data |
| 502 / slow after deploy | Render logs | usually Valkey/DB load on restart — transient; socket timeouts bound it |
| Scheduled job didn't run | `/health/` scheduler heartbeat | in-process scheduler covers light jobs; add free external pinger for heavy ones |
