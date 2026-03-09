# Platform apps — public API and single path

**Purpose:** Platform-oriented apps (platform_runtime, policies, registries, marketplace, tenancy, observability, etc.) are the **only** authorized path for their domain. Use their public APIs; do not bypass with direct DB or settings.

## platform_runtime

- **Public entry:** `build_tenant_runtime(ctx, request)` → `TenantRuntime`; `get_tenant_runtime(request)` via middleware sets `request.tenant_runtime`.
- **Use this:** `request.tenant_runtime` for policy, blueprint, flags, branding, integrations, marketplace, compliance, locale, modules. Helpers: `get_effective_site_settings(request)`, `get_effective_flags_for_school(school)`.
- **Not that:** Do not read `School.settings` / `School.features` or `SiteSettings.get_solo()` in tenant request path; use runtime or allowlisted helpers only. Lint: `scripts/lint_tenant_settings.py --check-get-solo-only --check-school-settings-features`.

## policies

- **Public entry:** `get_effective_policy(school, request=None)`; PolicyBundle, TenantBlueprint, BlueprintPack models; apply/rollback via marketplace or admin.
- **Use this:** Policy and blueprint data only via `get_effective_policy` or `request.tenant_runtime.policy_typed` / `runtime.blueprint`.
- **Not that:** Do not read policy-like data from `school.settings` or raw SiteSettings in tenant code.

## registries

- **Public entry:** EducationLevelRegistry, CountryRegistry, and other registries in `apps/registries`; runtime resolver step 3 compiles `RegistryContext`.
- **Use this:** Registry lookups via runtime (`runtime.registry`) or direct registry APIs where documented; structural config (terms, levels, types) from registries only.
- **Not that:** No hardcoded term lists or structural config from School.settings; use registries or blueprint/policy.

## marketplace

- **Public entry:** App catalog, installations, blueprint marketplace; runtime step 10 compiles marketplace context.
- **Use this:** Installed apps and blueprint catalog via `request.tenant_runtime.marketplace`; install/activate via control-plane or documented APIs.
- **Not that:** Do not install or configure apps outside marketplace flows; no direct writes to installation tables from tenant app code.

## tenancy

- **Public entry:** TenantContext, tenant resolution (middleware); Client, Domain models; provisioning via control-plane or signup.
- **Use this:** Tenant identity via `request.tenant_ctx`, `request.school`; tenant-scoped queries (schema_name / tenant_id).
- **Not that:** No tenant-path fallbacks that bypass runtime; no cross-tenant data access.

## siteconfig (integration / API Center)

- **Public entry:** `INTEGRATION_CATALOG`, `resolve_active_integration(school, service_key)`; ServiceIntegration model for credentials.
- **Use this:** Integration config via catalog and `resolve_active_integration`; runtime step 10 exposes `runtime.integrations`.
- **Not that:** Do not add integration types without updating INTEGRATION_CATALOG; do not read credentials from ad-hoc tables. See `docs/PROVIDER_REGISTRY_GOVERNANCE.md`.

## Contract tests

- Tenant apps must not import `runtime_resolver` internals (e.g. `_step*` functions) or read `school.settings`/`school.features` for behavior. Enforced by `scripts/lint_tenant_settings.py` and `apps/platform_runtime/tests/test_tenant_settings_lint.py`, `test_runtime_contract.py`.

## References

- `apps/platform_runtime/__init__.py` — public exports
- `docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md`
- `docs/PROVIDER_REGISTRY_GOVERNANCE.md`
- `docs/CONTROL_PLANE_BOUNDARY_RULES.md`
