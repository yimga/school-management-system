# Visual & dashboard UX bar (closed scope)

This document **replaces** the old “honest scope” caveat: there is now a **defined, repeatable bar** for manager host, marketing surfaces, and (on Postgres) tenant parent/teacher portals.

## One command (recommended before release)

```bash
bash scripts/full_ux_assurance.sh
```

This runs:

1. **`scripts/run_visual_qa.sh`** — Playwright against a local `runserver`:
   - **Public host** (`runmycampus.com`): marketing proof pages, no horizontal overflow, no 500.
   - **Manager host** (`manager.runmycampus.com`): super-admin login, backend, Setup Studio, super app catalog, control-plane scroll surfaces.
   - **Tenant host** (first `Client` + `Domain` when `DATABASE_URL` is **Postgres**): login as **teacher1** (staff intent) → `/portal/teacher/`; **Parent1** (parent) → `/portal/parent/`; overflow + screenshots.

2. **`scripts/pre_deploy_gate.sh`** with `SKIP_VISUAL_QA=1` — lints, migrations, smoke tests, theme matrix, multi-tenant unit tests, etc.

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| Node + `npm ci` | Playwright ships via devDependencies |
| Chromium | `npx playwright install chromium` (full_ux_assurance does this) |
| **Postgres + tenant + demo users** | For tenant portal tests: run `seed_render_users` (or equivalent) so **teacher1** and **Parent1** exist; password must match **`ADMIN_PASSWORD`** (or `VISUAL_QA_TENANT_PASSWORD`). |
| **SQLite** | No django-tenants domain → tenant portal block **skips**; manager + public QA still run. |

**Postgres first-time prep (tenant portal tests):**

```bash
export DATABASE_URL='postgresql://...'
export ADMIN_PASSWORD='your-seed-password'
python manage.py migrate --noinput
python manage.py migrate_schemas --tenant --noinput
python manage.py seed_render_users
export ADMIN_PASSWORD='your-seed-password'
bash scripts/full_ux_assurance.sh
```

Use a **non-production** DB for `runserver` + Playwright.

## Optional environment

| Variable | Purpose |
|----------|---------|
| `ADMIN_PASSWORD` | Same as Render seed → tenant Playwright logins. |
| `VISUAL_QA_TENANT_PASSWORD` | Overrides tenant demo password. |
| `VISUAL_QA_PORT` | Default `8010`. |
| `VISUAL_QA_SKIP_TENANT_PORTALS=1` | Skip teacher/parent portal tests even on Postgres (e.g. empty DB). **Not for production release sign-off.** |

## Artifacts

- Screenshots: `artifacts/visual-qa/<DATE>/{public,authenticated,tenant}/...`
- Server log: `artifacts/visual-qa/runserver.log`

## Human spot checks (2 minutes)

After the script passes, optionally tick [DASHBOARDS_AND_LINKS.md](./DASHBOARDS_AND_LINKS.md) § **Manual spot checklist** on staging: one backend link, one super sidebar link, one parent deep link.

## CI

- Gate-only jobs may use `SKIP_VISUAL_QA=1`.
- **Release / main**: run `full_ux_assurance.sh` on a Postgres workflow when you need full parity with production.
