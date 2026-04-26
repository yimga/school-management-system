# Production deployment checklist (RunMyCampus)

Use with `ENVIRONMENT_VARIABLES.md` and the provider runbook. This is a **governed sequence**, not a replacement for the execution ledger in `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`.

## Pre-flight

- [ ] `SECRET_KEY` set in environment (never commit).
- [ ] `DEBUG=0` in production.
- [ ] `ALLOWED_HOSTS` includes canonical host, `*.` tenant base, and any worker/render hostnames.
- [ ] `CSRF_TRUSTED_ORIGINS` includes `https` origins for the same; note Django does not use `*` the same as DNS wildcards in all versions—set explicit `https://` entries per `config/settings.py` logic.
- [ ] Database URL or discrete DB settings point at production **PostgreSQL** (not SQLite).
- [ ] `USE_DJANGO_TENANTS` and migration path understood (see `render.yaml` / `preDeployCommand` for Render).

## Deploy

- [ ] Run the **pre-deploy migration** path your environment defines (e.g. `./scripts/release/render_predeploy.sh` on Render when `USE_DJANGO_TENANTS=1`).
- [ ] `collectstatic` is part of your build or release script (e.g. `build.sh` / platform pipeline).
- [ ] Health check returns 200: `/health/` (primary; `render.yaml` `healthCheckPath`). Equivalents: `/ready/`, `/status/` (see `config/tenant_urls.py`).

## Post-deploy (smoke)

- [ ] Marketing or login page loads on public host.
- [ ] Login on a **school host** resolves `request.school` and loads portal/dashboard.
- [ ] Open Configuration Control Center on tenant: `/siteconfig/console/`.
- [ ] Open one read-only evidence page (e.g. term publish, academic years).
- [ ] 500s absent in log tail for the above (see `DEPLOYMENT_ROLLBACK.md` on failure).

## Post-deploy (operational)

- [ ] Error notifications path documented (log drain, email, Pager—whatever the org uses).
- [ ] Backups: confirm provider backup schedule; document restore test cadence in `DEPLOYMENT_ROLLBACK.md`.

## Related

- `STAGING_RELEASE_EXECUTION.md` for a **staged, ordered** run (predeploy → start → health → smoke).
- `RENDER_DEPLOYMENT_RUNBOOK.md` for Render-specific steps.
- `LAUNCH_SMOKE_TEST.md` and `RELEASE_NOTES_LAUNCH.md` for staging cutover and links to rollback.
- `../sales/DEMO_SCRIPT.md` for a **post-deploy** product smoke that mirrors GTM.
