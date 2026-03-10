# Resolver precedence chain

**Purpose:** Single documented order in which tenant behavior is resolved. Every resolver should follow this precedence when merging platform, region, blueprint, policy, plan, tenant, and sandbox values.

## Order (lowest to highest priority)

1. **Platform default** — Non-tenant values (e.g. default grading keys, default locale). Source: `SiteSettings.get_solo()` or `PlatformDefaults`; used when no tenant context.
2. **Registry / region** — Country, calendar, grade scale, terminology from global registries and region config. Source: registries, `RegionConfig`.
3. **Blueprint default** — Starter stack and composition from the tenant’s blueprint. Source: `TenantBlueprint`, blueprint packs.
4. **Policy bundle** — Behavioral rules (grading, attendance, billing, approval) from policy bundles attached to the tenant or region. Source: `PolicyBundle`, `get_effective_policy(school)`.
5. **Plan / entitlement** — Feature caps, add-ons, and plan-level overrides. Source: plans, entitlements (when implemented).
6. **Tenant override** — School-level `school.settings` / `school.features` and tenant-specific branding. Source: `School.settings`, tenant branding.
7. **Sandbox / staged override** — Unpublished or staged metadata for preview. Source: sandbox tables or staged packages (when implemented).

## Where it is implemented

- **Runtime build:** [apps/platform_runtime/runtime_resolver.py](apps/platform_runtime/runtime_resolver.py) — `build_tenant_runtime()` and steps (e.g. _step3_registry, _step4_blueprint, _step6_flags, _step7_branding) implement this order.
- **Policy merge:** [apps/policies/resolver.py](apps/policies/resolver.py) — `get_effective_policy(school)` merges platform defaults, country defaults, and tenant overrides.
- **Registry entry points:** [apps/platform_runtime/resolver_registry.py](apps/platform_runtime/resolver_registry.py) — Lists RuntimeResolver, BlueprintResolver, PolicyResolver, BrandingResolver, etc.

## Observability

**What's driving this?** — GET `/api/observability/runtime-inspect/` (staff/superuser only) returns JSON with resolver registry, tenant identity, and `resolved_sources`: `source_blueprint_id`, `source_policy_bundle_id`, `applied_overrides`, `compilation_trace`, `compilation_timestamp`, `warnings`. Implemented in [observability.views.runtime_inspect](apps/observability/views.py).
