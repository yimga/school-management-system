# Staging release — execution checklist

**Purpose:** Turn repository deployment docs into an **actionable, ordered** list for a **Render (or equivalent) staging** cutover. This document does **not** confirm that a specific environment was deployed; operators tick boxes during the run.

**Related:** `PRODUCTION_DEPLOYMENT_CHECKLIST.md`, `RENDER_DEPLOYMENT_RUNBOOK.md`, `ENVIRONMENT_VARIABLES.md`, `LAUNCH_SMOKE_TEST.md`, `DEPLOYMENT_ROLLBACK.md`, `RELEASE_NOTES_LAUNCH.md`.

---

## 1. Pre-deploy checklist

- [ ] **Branch / commit** tagged or recorded (SHA written in ticket).
- [ ] **Secrets:** `SECRET_KEY` present for staging; never committed.
- [ ] **DEBUG** `0` for staging web/worker/beat.
- [ ] **Database:** `DATABASE_URL` (or `DB_HOST`+`DB_NAME`+`DB_USER`+`DB_PASSWORD`+`DB_PORT`) points to **staging Postgres** — not local SQLite, not production DB.
- [ ] **Multi-tenant:** `USE_DJANGO_TENANTS` matches the migration path you will use (`1` → schema migrations via predeploy; see below).
- [ ] **Hostnames:** Staging `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` **manually** updated for this environment (see section 10).
- [ ] **Email:** If you need real mail from staging, set `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` in the dashboard; otherwise accept console/dummy behavior per settings.

## 2. Required environment variables (minimum)

| Area | Variables |
|------|-----------|
| Core | `SECRET_KEY`, `DEBUG=0`, `DJANGO_SETTINGS_MODULE=config.settings` (workers/beat in `render.yaml`; web via WSGI) |
| HTTP / CSRF | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SECURE_SSL_REDIRECT` (see `render.yaml` pattern) |
| DB | `DATABASE_URL` (preferred) or composite `DB_*` per `config/settings.py` |
| Multi-tenant | `MULTI_TENANT_BASE_DOMAIN`, optional `MULTI_TENANT_LEGACY_BASE_DOMAINS`, `USE_DJANGO_TENANTS` |
| Cookies (subdomain tenants) | `SESSION_COOKIE_DOMAIN`, `CSRF_COOKIE_DOMAIN` (if using parent domain) |
| Async (if workers enabled) | `REDIS_URL`, `CELERY_BROKER_URL` |
| Web runtime | `PORT` (Render sets), optional `GUNICORN_APP_MODULE`, `RUN_STARTUP_SCHEMA_CHECK` (see `scripts/release/render_start_web.sh`) |

Full reference: `ENVIRONMENT_VARIABLES.md`.

## 3. Render deploy steps (align with `render.yaml`)

1. **Build:** `./build.sh` (venv, `pip install -r requirements.txt`, `collectstatic --noinput`).
2. **Pre-deploy command:** `./scripts/release/render_predeploy.sh` (see expectations below). **Do not** swap for plain `migrate` when `USE_DJANGO_TENANTS=1`.
3. **Start (web):** `bash ./scripts/release/render_start_web.sh` → Gunicorn `config.wsgi:application` with `config/gunicorn.conf.py`, bind `0.0.0.0:$PORT`.
4. **Workers/beat:** Use same `DATABASE_URL` and broker settings as web; start commands in `render.yaml`.

## 4. Predeploy command expectations

`./scripts/release/render_predeploy.sh` (read the file for `SKIP_DB_MIGRATIONS`, `APPLY_UI_FIXTURE_ON_DEPLOY`, etc.):

- **Migrations:** If `USE_DJANGO_TENANTS=1` — `migrate_schemas --shared` → `ensure_tenant_schemas` → `migrate_schemas --tenant` (twice) → `migrate_schools_to_tenants` → (later) tenant migrate again before UI import. If not tenant mode — `migrate --noinput` when `SKIP_DB_MIGRATIONS` is not `1`.
- **Backfill (when on):** `backfill_schooldomain`.
- **Checks:** `check_tenant_runtime` (when `RUN_STARTUP_SCHEMA_CHECK` not disabled).
- **Seeds / config:** `seed_admin_dashboard_palettes`; optional `import_ui_config` from `fixtures/ui_config.json` when `APPLY_UI_FIXTURE_ON_DEPLOY=1` and file exists; `normalize_ui_config`.
- **Preflight:** `integration_preflight` when `RUN_INTEGRATION_PREFLIGHT=1`.
- **Users:** `seed_render_users` (super-admin; tenant demo users only with `ADMIN_PASSWORD` set, per command help).
- **Catalog (when on):** `bootstrap_platform_catalog` (full or minimal per env).
- **Static:** `collectstatic --noinput --clear` (second collect after build).
- **DB health (when `scripts/release/run_health_check.sh` exists):** runs as bash.
- **Optional Collabora:** if `RUN_COLLABORA_READINESS_CHECK=1` and `COLLABORA_BASE_URL` set, runs `scripts/verify_collabora_wopi_smoke.py`.

**Expectation:** Command exits **0**; if not, **do not** mark deploy healthy—see `DEPLOYMENT_ROLLBACK.md`.

## 5. Web start command expectations

- Gunicorn loads **`config.wsgi:application`**.
- If `RUN_STARTUP_SCHEMA_CHECK` is not `0`, `manage.py check_tenant_runtime` runs **before** binding (see `render_start_web.sh`).

## 6. Health checks (after instance is up)

On the **tenant** URLConf, these paths are available (see `config/tenant_urls.py`):

| Path | Use |
|------|-----|
| `/health/` | **Primary** — matches `render.yaml` `healthCheckPath`. |
| `/ready/` | Same health view wired for readiness probes. |
| `/status/` | Same public health view; use for human/debug; prefer `/health/` for the platform’s health check. |

**Pass criteria:** HTTP **200** (or your proxy’s expected success) for GET.

## 7. Smoke test sequence

Execute **`docs/deployment/LAUNCH_SMOKE_TEST.md`** line by line on a **school host** with a known user. Do not treat marketing-only host as sufficient for full tenant steps.

**Minimum bar before “staging OK”:** Re-login after step 2 if you logged out. Complete **3–6** (portal through evidence), then **7** (bulk letters) if entitled or record 403/redirect, then **8–11** (Student 360 through Studio OS) without 5xx when in scope; **12** (report library) optional; **13** (tenant Advanced/Admin) for staff/superuser; **14** (permission / blocked) with a user missing `settings.manage` when testing denials. No single step should hard-fail the cutover for optional surfaces—record skips.

## 8. Rollback trigger criteria

Rollback or stop promotion if any of the following:

- Predeploy or start command **fails** (non-zero exit).
- **Health** endpoints fail after reasonable warm-up.
- **Smoke** fails on login, tenant resolution, or core CCC/evidence 500s.
- **Sustained 5xx** on primary flows after deploy.

**Procedure:** `DEPLOYMENT_ROLLBACK.md` (redeploy previous build; database restore only with DBA and backup).

## 9. Post-deploy verification

- [ ] **Logs:** No recurring 500s on the paths in `LAUNCH_SMOKE_TEST.md`.
- [ ] **Tenant resolution:** A request to `https://<staging-subdomain>.<base>/` sets `request.school` as expected.
- [ ] **CSRF:** No CSRF 403 on legitimate POSTs from the staging origin (origins in `CSRF_TRUSTED_ORIGINS`).
- [ ] **Celery (if used):** Worker process healthy; spot-check one scheduled or async path if in scope.
- [ ] **Ticket:** Note SHA, time, and operator name.

## 10. Manual values to replace (per staging environment)

Do **not** copy production `render.yaml` hostnames into a new staging service without editing.

| Item | What to set |
|------|-------------|
| **Service hostname** | e.g. `https://<your-service>.onrender.com` or your custom staging domain. |
| **ALLOWED_HOSTS** | Comma list: base domain, leading-dot wildcard form if used, **onrender** hostname, any manager host. |
| **CSRF_TRUSTED_ORIGINS** | Comma list of `https://` origins for every browser origin that will POST (include `https://*.<base>` only if your Django/version supports the wildcard you use; when in doubt, add explicit `https://<sub>.<base>`.). |
| **DATABASE_URL** | Staging **Postgres** connection string from the provider. |
| **SECRET_KEY** | Unique per environment; rotate if reusing a leaked value. |

**Reference blueprint:** `render.yaml` (update names/hosts for **your** staging service, not production).

## Sign-off (optional)

| Field | Value |
|-------|--------|
| Date | |
| Staging host | |
| Commit SHA | |
| Operator | |
| Smoke (LAUNCH_SMOKE_TEST) | Pass / Fail |
| Follow-ups | |
