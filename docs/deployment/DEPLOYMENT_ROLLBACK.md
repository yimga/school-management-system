# Rollback and recovery (production)

## Principles

- **No fake rollback**: a rollback is a **documented, repeatable** return to a known good state, not a narrative.
- Prefer **forward fix** for schema issues when migration already applied; use **revert deploy** for code/config only failures.

## When to rollback the deploy (code / config)

- Smoke test fails: login, health check, or tenant resolution broken after a release.
- Error rate spike in logs (5xx) tied to the new build.

**Steps (Render-style)**

1. In Render (or your host), **redeploy the previous active image/commit** the platform still has cached, or `git revert` + redeploy.
2. Confirm `DEBUG=0` and env vars were not accidentally wiped on rollback.
3. Re-run the production smoke: `/health/`, public home, one tenant URL, one evidence page.

## When to rollback database (rare)

- Only when a migration introduced **data loss** or **inconsistent state** and a backup restore is the least-risk path.

**Steps**

1. **Stop** web and workers to prevent new writes.
2. Restore from last **verified** backup (point-in-time if available); confirm with the DBA or provider console.
3. Re-run `preDeployCommand` / migration sequence for the **restored** schema version if needed.
4. Bring web up; run smoke and compare row counts for critical tables if the incident involved data.

## Migrations: forward-only discipline

- Do **not** delete migration files from the repo to “fix” production.
- Add a **new** migration to correct schema if a bad migration shipped.

## Backups

- Rely on **managed Postgres** automatic backups on Render; document RPO/RTO in your org’s internal ops doc.
- For restores, use provider docs (e.g. Render PostgreSQL recovery).

## Communication

- Log incident: time, build id, first error, scope (single tenant vs all), and decision (rollback vs hotfix).

## Launch smoke (after rollback or hotfix)

Use the list in `PRODUCTION_DEPLOYMENT_CHECKLIST.md` plus: login, dashboard, CCC, one evidence page, Student 360 if in scope, scheduled reports hub, marketplace catalog (if on), Studio OS, admin as Advanced-only demo, logout. See also `LAUNCH_SMOKE_TEST.md`.
