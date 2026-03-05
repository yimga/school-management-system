# Module Refactor Template (RunMyCampus Blueprint)

Use this pattern when refactoring any module to depend **only** on `request.tenant_ctx` and the Policy Registry.

## Rule

- **Tenant identity:** Use `request.tenant_ctx` (or `request.school` where already set by middleware). Do not resolve tenant from host/session inside the module.
- **Behavior:** Use `apps.policies.registry.get_tenant_blueprint(request)` or `apps.policies.resolver.get_effective_policy(school, user=request.user, capability=...)` for labels, features, workflows, grading. Do **not** read `school.settings` or `school.features` directly in business logic.
- **Feature checks:** Use `get_effective_policy(school, user=..., capability="feature_code")["enabled"]` or keep using `is_feature_enabled(school, code)` (which is now backed by the resolver when used via the feature gate).

## Where context is used

- **Middleware:** `TenantContextMiddleware` sets `request.tenant_ctx`. Use it for tenant identity and host.
- **Templates:** `tenant_ctx` and `global_env` are injected by `apps.policies.context_processors.tenant_policy_context`. Use `global_env` for terminology, workflows, features in templates.
- **Views:** Call `get_tenant_blueprint(request)` or `get_effective_policy(request.school, request.user)` for validation rules, required fields, steps.
- **Feature gates:** `FeatureGatekeeperMiddleware` uses `get_effective_policy(school, user=request.user, capability=code)` for path-based feature checks.

## Adding new blueprint keys

1. In `apps.policies.resolver.get_effective_policy`, merge the new key from `school.settings` or `school.features` (or a future TenantBlueprint model) into the returned dict.
2. Document the key in this file or in the registry docstring.
3. Use the key in the module via `get_effective_policy(...)[key]` or `global_env.key` in templates.

## Tests

- Prove cross-tenant leakage fails (attempt to access another tenant’s data → 403/404).
- Prove policy locks enforced (e.g. disabled feature returns 403).
- Prove module behavior changes under two different blueprints (e.g. two schools with different settings produce different allowed actions or labels).
