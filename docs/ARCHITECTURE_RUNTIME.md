# Runtime is the law — architecture rules

**Purpose:** Canonical project rules for a metadata-governed, runtime-resolved platform. No tenant-specific branches or direct config bypass in tenant-facing code.

## Rules

1. **Runtime is the law.** Tenant behavior is determined by the **resolved runtime** for the request (policy, blueprint, branding, entitlements), not by ad-hoc `SiteSettings.get_solo()` or direct `school.settings` / `school.features` in tenant-facing views, serializers, or tasks. Use `get_effective_site_settings(request=request)`, `get_effective_policy(school)`, `get_effective_branding(request)`, and `request.tenant_runtime` (see [platform_runtime.helpers](apps/platform_runtime/helpers.py) and [policies.resolver](apps/policies/resolver.py)).

2. **No tenant-specific branches.** Do not hard-code tenant slugs, tenant domains, or region/currency literals in application code. Use the domain resolution service ([apps/schools/domain_resolution_service.py](apps/schools/domain_resolution_service.py)), registries, and env/config for defaults. CI flags new violations (see [lint_tenant_settings.py](scripts/lint_tenant_settings.py)).

3. **One injection path.** All modules get policy/blueprint/branding via the same path: middleware sets `request.tenant_runtime`; views and services use `get_effective_*` helpers or `request.tenant_runtime`. Documented in [ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md](architecture/ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md).

4. **Resolvers and precedence.** Resolution order: platform default → registry/region → blueprint → policy bundle → plan/entitlement → tenant override → sandbox. Implemented in [platform_runtime.runtime_resolver](apps/platform_runtime/runtime_resolver.py) and [resolver_registry](apps/platform_runtime/resolver_registry.py). See [docs/architecture/RESOLUTION_CHAIN.md](architecture/RESOLUTION_CHAIN.md) for the full chain.

## Enforcement

- **CI:** `scripts/lint_tenant_settings.py` (get_solo, school.settings/features, hardcoded region/currency) runs in pre_deploy_gate. `apps/platform_runtime/tests/test_tenant_settings_lint.py` fails if new violations appear in tenant apps.
- **Audits:** [SITESETTINGS_INVENTORY.md](security/SITESETTINGS_INVENTORY.md), [CSRF_EXEMPT_AUDIT.md](security/CSRF_EXEMPT_AUDIT.md), [ALLOWANY_API_AUDIT.md](security/ALLOWANY_API_AUDIT.md).

## References

- [Documentation governance](documentation_governance_plan.md)
- [UX plan completion register](plan/UX_PLAN_FULL_COMPLETION_REGISTER.md)
- [Metadata-driven plan status](plan/METADATA_DRIVEN_PLAN_STATUS.md)
