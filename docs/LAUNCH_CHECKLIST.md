# Launch Checklist (Phase Deploy)

Pre-go-live verification for multi-tenant deployment. Run these before considering the system ready for production.

## Schema & DB

- **Migrations:** `python manage.py migrate --noinput` (or `migrate_schemas --shared` / `migrate_schemas --tenant` when using django-tenants). Predeploy script [scripts/release/render_predeploy.sh](scripts/release/render_predeploy.sh) runs this unless `SKIP_DB_MIGRATIONS=1`.
- **Health check:** `python manage.py db_health_check` (if available) or `python manage.py check --deploy`. [scripts/release/run_health_check.sh](scripts/release/run_health_check.sh) is invoked at end of predeploy.
- **Data isolation (multi-tenant):** Verify schema A cannot see schema B data (run tenant isolation tests). When single-schema: ensure all tenant-scoped queries use `school_id` / RLS.

## Static & Compression

- **Static assets:** `python manage.py collectstatic --noinput` (verify themes/assets bundled).
- **Brotli/Gzip:** Ensure partials and static are served with compression (e.g. WhiteNoise, CDN, or Nginx/Caddy).

## SSL & DNS

- **Wildcard DNS:** `*.platform.com` (or your base domain) for subdomain tenants.
- **TLS:** Caddy (on-demand) or Nginx + certbot; or Cloudflare for SaaS for edge TLS.

## Application Start

- **Web start:** Use [scripts/release/render_start_web.sh](scripts/release/render_start_web.sh) so Gunicorn binds `0.0.0.0:$PORT` (required on Render). Set Render web service start command to: `bash ./scripts/release/render_start_web.sh` (after predeploy runs migrate).

## CI/CD (recommended)

- Run tests (optionally in a dummy tenant schema when using schema-per-tenant).
- In pipeline: run `migrate --noinput` (or `migrate_schemas`) before app start; run `check --deploy`.
- Build image after tests pass; deploy with predeploy then web start.

## IaC (Terraform / equivalent)

- Document `terraform init`, `plan`, `apply` for global registry and regional cells if used.
- Data residency: pin EU/Quebec etc. to nearest region; document release script that runs migrations before app start.

## Regional & Branding

- **Regional terms:** Onboarding uses country/sub_system and education profiles; verify regional terms in wizard.
- **Branding on login:** Login page uses tenant/site branding (logo, primary color) when resolved.

## Offline & Sync (if enabled)

- **Offline sync stress test:** Verify sync conflict handling and queue behavior under load.
- **Sequence sync:** Run `sync_tenant_sequences` (or equivalent) after migration if using per-tenant sequences.

## Quick reference

| Step              | Command / check                                      |
|-------------------|------------------------------------------------------|
| Migrate           | `python manage.py migrate --noinput`                 |
| Deploy check      | `python manage.py check --deploy`                     |
| Predeploy (full)  | `bash scripts/release/render_predeploy.sh`           |
| Web start         | `bash scripts/release/render_start_web.sh`           |
