# Management commands index

**Purpose:** Central index of Django management commands. Each command should have a docstring; critical and deploy-related commands are smoke-tested in CI where possible.

## Platform / tenant bootstrap

| Command | App | Purpose |
|---------|-----|--------|
| `migrate` | Django | Apply migrations. Run before any app. |
| `ensure_superuser` | accounts | Create/update platform superuser (admin/admin or env). |
| `ensure_default_tenant_admin` | accounts | Ensure tenant admin for `--slug` or first tenant; use instead of ensure_gilead_admin. |
| `ensure_gilead_admin` | accounts | Deprecated alias for ensure_default_tenant_admin. |
| `seed_render_users` | accounts | Release command: superuser + tenant admin + optional demo users (ADMIN_PASSWORD). |
| `create_teacher_parent_accounts` | accounts | Create teacher/parent/principal demo accounts. |
| `ensure_tenant_schemas` | customers | Ensure DB schemas exist for tenants (django-tenants). |

## Tenant / school ops

| Command | App | Purpose |
|---------|-----|--------|
| `tenant_health_check` | schools | Check tenant by --slug/--domain/--schema (PostgreSQL). |
| `tenant_wind_down` | schools | Wind down a tenant. |
| `migrate_schools_to_tenants` | schools | One-off migration of schools to tenant schemas. |
| `migrate_tenant_schemas_one_by_one` | schools | Migrate tenant schemas. |

## Site config / registries

| Command | App | Purpose |
|---------|-----|--------|
| `bootstrap_runmycampus_platform` | siteconfig | Bootstrap platform catalog and defaults. |
| `seed_global_regions` | siteconfig | Seed region registry. |
| `seed_admin_dashboard_palettes` | siteconfig | Seed admin dashboard theme palettes. |
| `seed_blueprint_policy_packs` | policies | Seed blueprint and policy packs. |
| `seed_migration_profiles` | automation | Seed migration cloud profiles. |
| `seed_marketplace_apps` | marketplace | Seed marketplace app catalog. |
| `verify_registry_coverage` | registries | Verify registry coverage. |

## Observability / health

| Command | App | Purpose |
|---------|-----|--------|
| `db_health_check` | observability | DB connectivity check. |
| `synthetic_probe` | observability | Synthetic probe (optional DB check). |
| `marketplace_health_check` | marketplace | Task/command for installation health. |

## Compliance / security

| Command | App | Purpose |
|---------|-----|--------|
| `security_log_retention` | accounts | Apply audit log retention. |
| `privacy_request` | compliance | Process privacy requests. |
| `check_compliance` | compliance | Compliance checks. |
| `archive_old_audits` | compliance | Archive old audit logs. |

## Runbooks

See `docs/RUNBOOKS_INDEX.md` for incident, deploy, rollback, and failure-mode runbooks.

## Smoke / CI

- Critical path: `migrate`, `ensure_superuser`, `ensure_default_tenant_admin` (with --help or dry run), `seed_render_users` (docstring).
- Lint: `scripts/lint_tenant_settings.py --check-get-solo-only --check-school-settings-features` should pass for tenant apps.
