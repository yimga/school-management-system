# Render deployment runbook

This runbook matches the **Render Blueprint** in the repository root `render.yaml`. Adjust names if your Render service or database differ.

## Services (from `render.yaml`)

- **Web**: Python, `buildCommand` → `./build.sh`, `preDeployCommand` → `./scripts/release/render_predeploy.sh`, `startCommand` → `bash ./scripts/release/render_start_web.sh`.
- **Worker / Beat** (if enabled): use the same env as web for Django settings and broker URL.
- **PostgreSQL** and **Redis** as linked services for `DATABASE_URL` and `REDIS_URL` / `CELERY_BROKER_URL`.

## Critical: migrations with `USE_DJANGO_TENANTS=1`

- **Do not** replace `preDeployCommand` with plain `manage.py migrate` on the tenant product without checking `render.yaml` comments.
- The predeploy script must run the **shared** then **tenant** migration path expected by the project (see `scripts/release/render_predeploy.sh`).

## Health

- `healthCheckPath: /health/` on the web service (`render.yaml`).
- Same view is wired at `/ready/`; `/status/` is also available on tenant URLConf (`config/tenant_urls.py`). Prefer `/health/` for Render’s health check.

## Environment (minimum)

- `DEBUG=0`
- `SECRET_KEY` (generate in Render or provide securely)
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` aligned with the public hostname
- `DATABASE_URL` from Render Postgres
- `MULTI_TENANT_BASE_DOMAIN` and cookie domains if using subdomain tenants

## Post-deploy

1. Open the service URL; confirm 200/302 to login.
2. Open manager host and one school subdomain; confirm tenant resolution.
3. Tail logs for 500s during first sign-in and first evidence page.

## If deploy fails

- See `DEPLOYMENT_ROLLBACK.md`.
- Re-run predeploy in a one-off shell only after reading the error (migration vs static vs start command).

## Related internal docs

- `docs/RENDER_AFTER_MASTER_CHECKLIST_DEPLOY.md` (post-merge checklist, if still current).
- `build.sh` and `scripts/release/render_start_web.sh` for exact start behavior.
