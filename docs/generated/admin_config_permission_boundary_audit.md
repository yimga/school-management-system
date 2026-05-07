# Admin Configuration Permission Boundary Audit

| Check | Evidence | Status |
|---|---|---|
| Platform-only routes require platform/control-plane access | `/super/` routes use `require_super_access_with_host`; `/configuration/` views use `require_control_plane_access` | pass |
| Tenant routes require tenant context | School configuration, blueprint setup, and pack setup require `request.school` and `tenant_operator_hub_eligible` | pass |
| Tenant cannot access `/configuration/` | Tenant URLConf routes `/configuration/` to `tenant_configuration_forbidden`; administration model test asserts 403 | pass |
| Tenant cannot view global registries | Tenant school configuration renders tenant sections only; tests assert no global registry/system closure strings | pass |
| Tenant cannot access other tenants' installs/requests | Tenant pack setup filters installations by `school`; rollback/deactivate uses `get_object_or_404(..., school=school)` | pass |
| `/internal-admin` remains fallback | `internal_admin_alias_redirect` redirects to `/admin/` and preserves path/query | pass |
| `/admin` compatibility preserved | Platform and manager URLConfs use `platform_admin_site`; tenant URLConf uses `tenant_admin_site` | pass |
| External dependencies are honest | Preview engines carry `external_required`; billing is marked `external_required` in configuration catalog | pass |
| Sensitive apply/rollback emits audit | Blueprint and pack apply/rollback services emit audit events | pass |
| School aliases do not expose platform configuration | `/school/apps/`, `/school/billing/`, `/school/money/`, `/school/workflows/`, `/school/offline/`, `/school/audit/`, `/school/security/` redirect to tenant-safe surfaces only | pass |

Residual risks: some tenant-safe routes are aliases to existing product surfaces, and billing/PSP live readiness remains blocked on external proof.
