# Deploying on Render.com

For a full map of dashboards and links, see [DASHBOARDS_AND_LINKS.md](./DASHBOARDS_AND_LINKS.md).

## Host and CSRF (required for login to work)

- **ALLOWED_HOSTS:** When `RENDER=true` (set by Render), the app automatically allows `*.onrender.com`. You do not need to set `ALLOWED_HOSTS` in the Render dashboard unless you use a custom domain.
- **CSRF / HTTPS:** The app sets `SECURE_PROXY_SSL_HEADER` and builds `CSRF_TRUSTED_ORIGINS` from `RENDER_EXTERNAL_HOSTNAME` (set by Render). Login POST and all forms work over HTTPS. If you use a custom domain, set `CSRF_TRUSTED_ORIGINS=https://your-domain.com` in Render environment.

## Main URLs (after deploy)

| Purpose        | URL (replace `YOUR-SERVICE` with your Render host) |
|----------------|----------------------------------------------------|
| **Landing / Login** | `https://YOUR-SERVICE.onrender.com/` → redirects to login |
| **Login page**     | `https://YOUR-SERVICE.onrender.com/authentication/login/` |
| **Parent portal**  | `https://YOUR-SERVICE.onrender.com/portal/parent/` |
| **Teacher (portal)** | `https://YOUR-SERVICE.onrender.com/portal/teacher/` |
| **Teacher (evals)**  | `https://YOUR-SERVICE.onrender.com/evals/teacher/` |
| **Frontend admin dashboard** | `https://YOUR-SERVICE.onrender.com/backend` → redirects to `/authentication/backend/` |
| **Django admin**    | `https://YOUR-SERVICE.onrender.com/admin/` |

Example for `school-management-system-2kzk.onrender.com`:

- Login: https://school-management-system-2kzk.onrender.com/authentication/login/
- Parent: https://school-management-system-2kzk.onrender.com/portal/parent/
- Teacher: https://school-management-system-2kzk.onrender.com/evals/teacher/
- Frontend admin: https://school-management-system-2kzk.onrender.com/backend
- Backend admin: https://school-management-system-2kzk.onrender.com/admin/

## Database and credentials (important)

If you do **not** set `DATABASE_URL`, the app uses SQLite on the server disk. Render’s disk is **ephemeral**: it is wiped on every deploy, so **all users and data disappear** after each deploy.

- **Use PostgreSQL:** In Render, create a PostgreSQL database and set **`DATABASE_URL`** to its **Internal Database URL** in your Web Service → Environment (paste the full URL from the Postgres service). If you use separate vars instead, set real values for `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT` (do not use placeholder text like `from_render` or the app may fall back to SQLite and migrations can fail).
- **Recreate users on each deploy:** Use pre-deploy orchestration to run migrate, UI seeds, integration preflight, and render user seeding in one place.
  - Blueprint (`render.yaml`) now uses: `./scripts/release/render_predeploy.sh`
  - Non-Blueprint Release Command equivalent: `./scripts/release/render_predeploy.sh`

## Optional env vars on Render

- `ALLOWED_HOSTS` – Only if you add a custom domain (e.g. `yourapp.com,.onrender.com`).
- `CSRF_TRUSTED_ORIGINS` – Only if you use a custom domain (e.g. `https://yourapp.com`).
- `DEBUG=0` – Recommended in production.
- `DATABASE_URL` – **Recommended.** PostgreSQL Internal Database URL so data and users persist across deploys.
- `ADMIN_PASSWORD` – Password for the `admin` account created by the release command.
- `SECRET_KEY` – Required in production.
- `RUN_INTEGRATION_PREFLIGHT=1` – Recommended. Fails deploy only when enabled integration features are missing runtime credentials.
- `ADMIN_PASSWORD` – Recommended. Enables automatic `seed_render_users` during predeploy.
- `RUN_BOOTSTRAP_PLATFORM_CATALOG=1` – Optional. When set, predeploy runs **full** bootstrap (`bootstrap_platform_catalog --all`) by default so Manager catalogs, registries, workflow/dashboard packs, provider registry, migration profiles, portal FAQs/KB, and finance defaults are populated. See [BOOTSTRAP_PLATFORM_CATALOG.md](./BOOTSTRAP_PLATFORM_CATALOG.md).
- `RUN_MINIMAL_BOOTSTRAP=1` – Optional. When `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`, set this to run only blueprint + marketplace seed (no registries, workflow/dashboard, portal, etc.). Omit or set to `0` for full bootstrap.

**First-time / living platform:** Set `RUN_BOOTSTRAP_PLATFORM_CATALOG=1` on first deploy; full bootstrap runs by default, so Manager is not a ghost town. See [SEEDING_BOOTSTRAP_AUDIT.md](./SEEDING_BOOTSTRAP_AUDIT.md).

## Start command (do not override without binding to PORT)

The web service **must** listen on **`0.0.0.0:$PORT`** so Render’s health check can detect an open HTTP port. The blueprint uses:

- **Start command:** `bash ./scripts/release/render_start_web.sh`

That script runs Gunicorn with `config/gunicorn.conf.py`, which sets `bind = "0.0.0.0:{PORT}"`. If you override the start command in the Render dashboard, use either this script or run Gunicorn with `-c config/gunicorn.conf.py` (or pass `--bind 0.0.0.0:$PORT` explicitly). Binding only to `127.0.0.1` or omitting `--bind` will cause “No open HTTP ports detected” and deploy failure.

## Predeploy flow

`scripts/release/render_predeploy.sh` performs (see script for env toggles):

1. **Migrations:** `migrate_schemas --shared` + `ensure_tenant_schemas` + `migrate_schemas --tenant` + `migrate_schools_to_tenants`, then **second** `migrate_schemas --tenant` (covers new school schemas). Non-tenant: `migrate --noinput`.
2. `seed_admin_dashboard_palettes`
3. Optional UI fixture import (`APPLY_UI_FIXTURE_ON_DEPLOY=1`) + tenant migrate before import when tenant mode
4. `normalize_ui_config`
5. `integration_preflight` (when `RUN_INTEGRATION_PREFLIGHT=1`)
6. **`seed_render_users`** — when `USE_DJANGO_TENANTS=1`, runs **`migrate_schemas --tenant`** again immediately before seeding so tenant tables (e.g. `people_teacherprofile.updated_at`) match models even if an earlier step was skipped.
7. `collectstatic`, optional `bootstrap_platform_catalog`, health check.
