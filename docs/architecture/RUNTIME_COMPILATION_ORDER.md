# Tenant Runtime Compilation Order

The tenant runtime (`request.tenant_runtime`) is built in a **strict 13-step order**. No module should invent a different precedence.

## Order (single source of truth)

1. **Route context** — surface (marketing / control_plane / tenant_plane), preview, sandbox
2. **Tenant identity** — id, slug, schema_name, domain, plan, status
3. **Registry context** — country, subdivision, currency, timezone, locale, education_levels, education_system_types, terminology, document_types, fee_categories, grade_scale_families
4. **Blueprint** — structural operating model (id, code, family, default_dashboard_pack, default_workflow_pack, institution_type)
5. **Policy bundle** — typed sections (admissions, gradebook, finance, communication, compliance, portal, payroll, attendance, raw)
6. **Flags / entitlements** — feature toggles, plan modules, quotas, marketplace_allowed, sandbox_enabled
7. **Branding** — logo, crest, colors, portal_theme, report_theme, email_theme
8. **Workflows** — by_module (admissions, fee_approval, grade_publish, etc.)
9. **Dashboards** — by_role, by_section
10. **Integrations / marketplace** — payment_provider, messaging, installed_apps, widget_registry, workflow_actions
11. **Compliance / security** — consent, export_restrictions, retention, actor context, impersonation
12. **Module configs** — runtime.modules.admissions, gradebook, finance, portal, communication (compiled from policy + registry + workflow + dashboard)
13. **Freeze** — debug metadata (source_blueprint_id, applied_overrides, compilation_trace); runtime treated as immutable for the request

## Override precedence (platform-wide)

When merging policy/blueprint/tenant values, use this order:

1. Platform defaults  
2. Region / country defaults  
3. Blueprint defaults  
4. Policy bundle defaults  
5. Plan / entitlement constraints  
6. Tenant overrides  
7. Scheduled / temporary overrides  
8. Request-mode overlays (preview, sandbox, impersonation-safe masking)

## Implementation

- **Builder:** `apps/platform_runtime/runtime_resolver.build_tenant_runtime(tenant_ctx, request=..., school=..., policy=...)`
- **Contract:** `apps/platform_runtime/contracts.TenantRuntime` and section dataclasses
- **Cache:** Request-scope cache (one runtime per request); optional per-tenant segment cache via `apps/platform_runtime/cache.py`
- **Jobs:** `build_tenant_runtime_for_tenant(tenant, mode="job")` for background tasks

## Invalidation

When policy, blueprint, branding, workflow/dashboard assignment, entitlement, or marketplace install changes, invalidate tenant runtime cache via `apps.platform_runtime.cache.invalidate_tenant_runtime_cache(school_id)` and `invalidate_policy_and_runtime_caches(school)`.
