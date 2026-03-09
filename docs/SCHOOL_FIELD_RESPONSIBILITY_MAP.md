# School model — field responsibility map

**Purpose:** Clarify which School fields are identity, branding, config, features, billing, or workflow/dashboard defaults. Behavior for tenant request path must come from `request.tenant_runtime` (policy, blueprint, entitlements, module_config); only the resolver and `tenant_config` read/write `settings` and `features` for compilation.

## Field classification

| Field(s) | Responsibility | Notes |
|----------|----------------|-------|
| `id`, `slug`, `name`, `subdomain`, `custom_domain`, `custom_domain_verified` | **Identity** | Stay on School. |
| `default_region`, `country_code`, `subdivision`, `timezone`, `sub_system` | **Region/locale** | Stay on School; runtime registry/context derives from these. |
| `plan`, `addons`, `school_type` | **Plan / type** | Stay on School; entitlements and flags come from plan + runtime. |
| `settings` (JSONField) | **Config (storage only)** | Written only by `siteconfig.tenant_config`; read only by `policies.resolver` and `tenant_config` for compilation. No tenant request path may read `school.settings` for behavior — use `request.tenant_runtime.policy` or `request.tenant_runtime.modules`. |
| `features` (JSONField) | **Feature manifest (storage only)** | Written by `tenant_config` and optionally siteconfig views; read only by resolver for policy compilation. No tenant request path may read `school.features` for behavior — use `request.tenant_runtime.flags` or `request.tenant_runtime.entitlements`. |
| `logo_url`, `wallpaper_url`, `primary_color`, `accent_color`, `theme_choice`, `theme_pack`, `branding_metadata` | **Branding** | Stay on School; runtime resolves BrandingContext from these. |
| `default_workflow_slug`, `default_dashboard_slug` | **Workflow/dashboard defaults** | Stay on School; runtime workflows/dashboards resolve from these + assignments. |
| `billing_type`, `trial_end_date`, `waiver_note` | **Billing state** | Stay on School; may be moved to a dedicated billing model in a later refactor. |
| `is_active`, `is_approved`, `last_activity`, `is_frozen`, `frozen_reason`, `compliance_region` | **State / compliance** | Stay on School. |
| `parent_school`, `hierarchy_path`, `education_levels`, `education_system_types`, etc. | **Structure / registries** | Stay on School or FKs; runtime registry context may derive from these. |

## Rules

1. **Identity + FKs stay on School:** slug, name, subdomain, plan, theme_pack, default_region, etc. No new "god" fields; new behavior belongs in blueprint, policy, or runtime compilation.
2. **`settings` and `features`:** Only `apps/siteconfig/tenant_config.py` and `apps/policies/resolver.py` read or write these for compilation. All tenant-facing code uses `request.tenant_runtime` (or helpers) for behavior.
3. **Billing:** May be extracted to a `TenantBilling` or billing service later; for now remains on School.
4. **Campus:** Future; when added, introduce `Campus` model (FK to School) per SCHOOL_TENANT_CAMPUS_CANONICAL.md.

## References

- `docs/SCHOOL_TENANT_CAMPUS_CANONICAL.md`
- `docs/MODEL_TO_CANONICAL_MAPPING_REPORT.md`
- `apps/platform_runtime/contracts.py` (TenantRuntime)
- `scripts/lint_tenant_settings.py --check-school-settings-features` (CI gate)
