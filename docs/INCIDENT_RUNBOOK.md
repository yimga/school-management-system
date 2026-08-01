# Incident Runbook

First-response runbook for a production incident on RunMyCampus (the marketing
host, the `manager` control plane, or any tenant subdomain). It is deliberately
short and action-first; the deep procedures live in the linked runbooks and this
file is the index into them under pressure.

> Scope: what to do in the first minutes of a suspected outage or degradation —
> assess, contain, communicate, recover, learn. For planned changes see
> [`DEPLOY_PIPELINE_RUNBOOK.md`](DEPLOY_PIPELINE_RUNBOOK.md); for data loss /
> restore see [`DR_BACKUP_RESTORE_RUNBOOK.md`](DR_BACKUP_RESTORE_RUNBOOK.md); for
> the support-desk / status-page operating model see
> [`SERVICE_AND_SUPPORT_OPERATING_LAYER.md`](SERVICE_AND_SUPPORT_OPERATING_LAYER.md).

## Severity

| Sev | Meaning | Examples |
| --- | --- | --- |
| **SEV1** | Platform down or data at risk, many tenants | Site 5xx across hosts; login broken globally; suspected data loss or cross-tenant leak; payments double-charging |
| **SEV2** | Major feature broken or one tenant hard-down | A whole surface 500s; a school cannot take attendance/grades; a deploy regressed a core flow |
| **SEV3** | Degraded / partial, workaround exists | Slow pages; one non-critical job not running; a single report broken |
| **SEV4** | Minor, no user impact yet | Elevated error rate; a dead background job discovered before it bites |

A **suspected cross-tenant data leak is always SEV1**, regardless of blast radius.

## Roles (name them out loud, even if one person wears several)

- **Incident Commander (IC)** — owns the decision to declare, mitigate, roll back, and resolve. Not necessarily the person debugging.
- **Ops** — runs the commands (health checks, rollback, restore).
- **Comms** — owns customer-facing status and internal updates.

## First 15 minutes

1. **Confirm it's real.** Hit the health endpoint on the affected host:
   `GET /healthz/` (`config/urls.py` → `apps.observability.views.healthz`). It
   checks DB, cache, and the Celery broker / workers / beat / queue depth and
   returns **503** when a *configured* dependency is down — so a 503 tells you
   which layer, and a 200 pushes you toward app-level or a specific surface.
2. **Declare + assign IC** if impact is SEV1/SEV2. Start an incident channel/note; timestamp everything (all times UTC).
3. **Look at the signals.** Sentry (when `SENTRY_DSN` is configured) for the
   exception + first-seen time; `/metrics/` (Prometheus scrape, routed only when
   the metrics backend is configured — see `apps/observability/metrics.py`) for
   rate/latency; the SLO targets in [`OBSERVABILITY_SLO.md`](OBSERVABILITY_SLO.md)
   (`apps/observability/slo.py`) for what "normal" is.
4. **Ask "what changed?"** first — most incidents are a recent change.
   - **⚠️ Auto-deploy is OFF.** A merged fix is **not live** until someone
     manually deploys. Conversely, prod may be running an *older* build than
     `main`. Before you debug a "bug", confirm what is actually deployed — a
     symptom that looks like a code bug is often a **stale deploy**.
   - **⚠️ Stale service-worker cache.** After a deploy, a client can keep serving
     old cached HTML/JS until the service-worker `CACHE_VERSION` bumps. A "still
     broken after the fix shipped" report is frequently a cache issue, not the
     code. Verify against a hard-reloaded / incognito session before escalating.
   - **⚠️ CI does not gate.** The GitHub Actions budget is exhausted, so a red
     CI run may simply mean CI never ran — do **not** assume tests passed on the
     deployed commit. The real gate is local `scripts/pre_push_boundary_check.py`.
5. **Communicate.** For SEV1/SEV2, post to the public status page (a
   `PublicIncident` fans out to subscribers on save — see the status-page section
   of [`SERVICE_AND_SUPPORT_OPERATING_LAYER.md`](SERVICE_AND_SUPPORT_OPERATING_LAYER.md)).
   Say what's impacted, that you're on it, and when the next update lands. Update
   on cadence even when there's nothing new.

## Mitigate → recover

Prefer the fastest safe path back to service; root-cause after.

- **Roll back the deploy.** If the incident tracks a recent release, roll back
  rather than roll forward. Pick the matching playbook in
  [`rollback_runbooks/`](rollback_runbooks/) — `P0D` (fastest / data-safe) through
  `P5` — by blast radius and whether a migration is involved. **Never** reverse a
  migration blindly under pressure; a schema roll-back is its own procedure.
- **Data loss / corruption / tenant restore.** Follow
  [`DR_BACKUP_RESTORE_RUNBOOK.md`](DR_BACKUP_RESTORE_RUNBOOK.md). Rehearse the
  shape with `scripts/restore_drill.py` (a rolled-back restore drill) before a
  real cutover if time allows — but a real restore is operator-gated and
  irreversible, so the IC explicitly authorises it.
- **Tenant isolation event.** Prod isolation is schema-per-tenant (django-tenants).
  A suspected leak: freeze writes on the affected surface if you can, preserve
  logs, and do **not** run ad-hoc cross-tenant queries that could widen exposure.
- **Dead background job.** If a scheduled job silently isn't running, check it
  against the beat registry (`scripts/verify_beat_task_registry.py`) — a beat
  entry naming an unregistered task is a silent no-op, not an error in the logs.

## Resolve + learn

- **Resolve** only when health is green *and* verified from a real client
  session (not just a cached one). Update the status page to resolved.
- **Postmortem** for every SEV1/SEV2, blameless, within a few days: timeline,
  contributing causes, what detected it (and what should have), and concrete
  follow-ups with owners. If a class of failure had no gate, the top follow-up is
  usually *add the gate* (a CI/boundary check or a must-fire test), per the repo's
  standard-execution-loop preference for a permanent seal over a one-time fix.
- **Escalate** early rather than late: if you are past your comfort or the SLO
  error budget is burning fast, pull in a second responder and widen comms.

## See also

- [`RUNBOOKS_INDEX.md`](RUNBOOKS_INDEX.md) — index of all runbooks.
- [`DEPLOY_PIPELINE_RUNBOOK.md`](DEPLOY_PIPELINE_RUNBOOK.md) — how a change reaches prod (and how to roll it back).
- [`DR_BACKUP_RESTORE_RUNBOOK.md`](DR_BACKUP_RESTORE_RUNBOOK.md) — backups + restore.
- [`OBSERVABILITY_SLO.md`](OBSERVABILITY_SLO.md) — SLO targets / error budgets.
- [`SERVICE_AND_SUPPORT_OPERATING_LAYER.md`](SERVICE_AND_SUPPORT_OPERATING_LAYER.md) — support desk + public status page.
- [`rollback_runbooks/`](rollback_runbooks/) — per-severity rollback playbooks (P0D…P5).
