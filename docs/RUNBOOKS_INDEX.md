# Runbooks index

**Purpose:** Index of runbooks for major failure modes and operations. Each runbook should be updated when procedures change.

## Deploy and rollback

| Topic | Doc | Notes |
|-------|-----|--------|
| Deploy | Render/platform docs | Release command: `migrate --noinput && seed_render_users`. |
| Rollback | Platform docs | Revert deploy; DB migrations are forward-only — document rollback strategy per migration. |
| Fresh DB | docs/FRESH_DB_FIX.md | DB_FILE, clean SQLite path. |

## Failure modes

| Failure mode | Doc / location | Notes |
|--------------|----------------|-------|
| Tenant isolation concern | docs/CONTROL_PLANE_BOUNDARY_RULES.md | Control-plane vs tenant; no tenant data on manager host. |
| Migration failure | docs/MIGRATION_CLOUD_RUNBOOK.md | Migration cloud rollback, repair. |
| Auth / login | docs/PLATFORM_ACCESS_AND_CREDENTIALS.md | Admin, tenant admin, passwords. |
| SiteSettings / config | docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md | Where get_solo is allowlisted. |
| Health / observability | apps/observability/ | /health/, /healthz/, db_health_check; healthz returns 500 on DB failure. |

## Operational discipline

- **Audit logs:** Retention and query — see compliance app and security_log_retention command.
- **Management commands:** docs/MANAGEMENT_COMMANDS_INDEX.md.
- **Platform apps single path:** docs/PLATFORM_APPS_PUBLIC_API.md.

## References

- docs/MIGRATION_CLOUD_RUNBOOK.md
- docs/ACTIVATION_FLOWS.md
- docs/CONTROL_PLANE_BOUNDARY_RULES.md
- docs/PLATFORM_ACCESS_AND_CREDENTIALS.md
