# Release notes — launch bundle (RunMyCampus)

**Audience:** Engineering + GTM. **This is a product/operator summary**, not a substitute for the engineering ledger: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`.

## Major operator surfaces

- **Configuration Control Center (CCC)** — `siteconfig:console_domains_hub` (`/siteconfig/console/` on tenant). Outcome-oriented entry for configuration domains, links to operator hubs, Studio, and feature audit.
- **Backend dashboard** — `accounts:backend_dashboard` (entry via `/backend/` redirect on tenant). Staff operator home with shell and widget surfaces.
- **Feature control and tenant runtime** — Read/write feature flags (governed) and read-only **tenant runtime configuration hub** for effective settings snapshots.

## Evidence / control plane (read-only where stated)

- **Academic years & departments (setup evidence)** — Tenant-scoped lists; **Advanced/Admin** changelists use **tenant** `urlconf` for Django admin. Superuser-only admin strip last.
- **Term publish, config mutation audit, report output history, tenant report schedules, report templates catalog, bulk letters (operator)** — Real model-backed views; no simulated send/export on evidence pages.
- **Scheduled report delivery hub** — Lists `TenantReportSchedule` rows; links to related evidence and Studio report library; admin schedules last for superusers.
- **Region / metadata** — Region validation and metadata operator/dynamic field surfaces are CP-first; admin remains Advanced.

## Studio OS

- **Studio** namespace under `/studio/` — experience (customizer), output (report library), automation, and related panes. Legacy `/siteconfig/reports/` redirects to Output Studio with `pane=reports` where configured.

## Marketplace

- **Tenant app catalog** — `/settings/app-catalog/` (`tenant_app_catalog`). Install/scope flows are entitlement- and plan-aware; not a replacement for contract negotiation.

## Admin fallback policy

- **CP-first, always.** Django admin (tenant: `/admin/`) is for **edge CRUD, superuser, and integration** work. Product UX must not require admin for day-to-day school operations. Evidence pages label admin links as **Advanced/Admin** and place them **after** product links and tables.

## Remaining known partials (honest)

Aligned with SOT **§11.4** (authoritative). These batches remain **PARTIAL** until closed in the ledger; **do not** mark them DONE from passing a generic test bar alone:

- **1072, 1098** — Reports / Studio / evidence alignment depth (see SOT for current theme).
- **1100, 1101** — Marketplace–Studio / link-hygiene and follow-on classification work; strict tests can be green while ledger scope is still partial.

Representative other PARTIALs may also appear in **§11.4** (e.g. 1087 UI density, 1060-class cross-links). **Rule:** only update completion state when the SOT’s gates for that batch are met.

## Deployment prerequisites

- **Postgres** for staging/production; SQLite is a dev default when `DATABASE_URL` is unset in settings.
- **`USE_DJANGO_TENANTS`:** If `1`, use **`./scripts/release/render_predeploy.sh`**, not ad-hoc `migrate` only.
- **Static files:** `collectstatic` in `build.sh` before web serves traffic.
- **Health:** `/health/` (and `/ready/`, `/status/`) for smoke and load balancers.
- **Smoke:** `docs/deployment/LAUNCH_SMOKE_TEST.md` on a **real school host** with a **test user**.

## Related (same folder: `docs/deployment/`)

- **LOCKED STABLE / release test gate (full bar):** [RELEASE_TEST_POLICY.md](RELEASE_TEST_POLICY.md)
- **Smoke (staging / production):** [LAUNCH_SMOKE_TEST.md](LAUNCH_SMOKE_TEST.md)
- **Production checklist:** [PRODUCTION_DEPLOYMENT_CHECKLIST.md](PRODUCTION_DEPLOYMENT_CHECKLIST.md)
- **Rollback / recovery:** [DEPLOYMENT_ROLLBACK.md](DEPLOYMENT_ROLLBACK.md) (do not rename)
- **Env / Render runbook / blueprint:** [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md), [RENDER_DEPLOYMENT_RUNBOOK.md](RENDER_DEPLOYMENT_RUNBOOK.md), repository `render.yaml`
- **Staging (ordered run):** [STAGING_RELEASE_EXECUTION.md](STAGING_RELEASE_EXECUTION.md)
