# Policy injection

Where Policy Registry and tenant context are injected (middleware, context processors, services). Use these instead of reading `school.settings` / `school.features` directly in business logic.

## Middleware

- **apps.tenancy.middleware.TenantContextMiddleware**  
  Injects `request.tenant_ctx` (TenantContext: tenant_id, schema_name, school_id, country, timezone, feature_flags, policy_overrides, host). Does not call `get_effective_policy`; it only attaches the raw context. Must run after tenant/school is set (e.g. after TenantMiddleware or TenantSchemaSchoolBridgeMiddleware).

## Context processors

- **apps.policies.context_processors.tenant_policy_context**  
  Adds to every template:
  - `tenant_ctx`: from `request.tenant_ctx`
  - `global_env`: from `get_effective_policy(request.school, user=request.user)` (merged platform + region + tenant policy).  
  Templates and views should use `global_env` (and optional `tenant_ctx`) instead of reading `school.settings` or `school.features` directly.

## Resolver (single read path for school.settings/features)

- **apps.policies.resolver.get_effective_policy(school, user=None, capability=None)**  
  The only place that should read `school.settings` and `school.features` to build the merged policy. Returns a dict: terminology, grading, workflows, features, rtl, default_language, grading_scale, education_dna_preset, plus pass-through keys (report_labels, education_profile_code, payment_gateways, labels_map, education_profile, security_weights, security_grace_period_days).  
  Modules must use `get_effective_policy(school)` (or the registry) for behavior; they must not read `school.settings`/`school.features` in business logic.

## Registry (request-scoped)

- **apps.policies.registry.get_tenant_blueprint(request)**  
  Returns `get_effective_policy(tenant)` for the tenant/school attached to the request. Used when you have a request and need the full policy dict.

- **apps.policies.registry.get_policy_for_request(request)**  
  Wrapper that returns policy for the request’s tenant; used by code that has only request.

## Feature gate

- **apps.schools.models.is_feature_enabled(school, capability)**  
  Use for feature-flag checks. Backed by merged features (and school model); do not read `school.features` directly in modules.

## Services that use policy (read-only)

These call `get_effective_policy(school)` and use the returned dict; they do not read `school.settings`/`school.features`:

- Reports: `apps.reports.services` (report_labels, education_profile_code, report_labels overrides).
- Finance gateways: `apps.finance.gateways.registry` (payment_gateways).
- Accounts: `apps.accounts.views` (default_language), `apps.accounts.security_health` (security_weights, security_grace_period_days).
- Branding: `apps.siteconfig.brand_registry` (labels_map, education_profile.labels_map).

## Per-tenant policy caching (optional)

- Set **POLICY_CACHE_TTL** (seconds) in settings to enable caching of the full policy dict per school. When set, `get_effective_policy(school)` (with `capability=None`) is cached under key `policy:{school_id}`. Use Redis or another backend for production scale.
- Call **invalidate_policy_cache(school)** after updating `school.settings` or `school.features` (e.g. from a `post_save` signal on School) so the next request gets a fresh policy.

## Excluded (by design)

- **Writers / source of truth:** `apps.policies.resolver` (reads school.settings/features to build policy), `apps.siteconfig.tenant_config`, `system_morph`, signup_views, siteconfig views that **write** to school.settings/features.
- **Canonical model:** `apps.schools.models` (e.g. `_has_feature_fallback`, used by `is_feature_enabled`).
- **Tests** that assert on `school.settings` or `school.has_feature` for model/behavior.
