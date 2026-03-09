# Policy and blueprint — single resolver path

**Goal:** All tenant behavior from policy/blueprint comes from the runtime resolver output. No backfill from SiteSettings or school.settings/school.features in tenant path; versioning and audit for changes.

## Single path

- **Read:** Tenant code must not read policy-like or blueprint-like data from `School.settings`, `School.features`, or `SiteSettings.get_solo()`. Use `request.tenant_runtime.policy_typed`, `request.tenant_runtime.blueprint`, or `get_effective_policy(school, request)` only.
- **Write:** Policy and blueprint changes (apply bundle, apply blueprint, rollback) go through policies app and marketplace; create version/snapshot and audit event where implemented.
- **Backfill:** Resolver may use allowlisted backfill only for control-plane or migration paths; tenant request path must not depend on backfill. See items 1–3 and docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md.

## Enforcement

- Lint: `scripts/lint_tenant_settings.py --check-school-settings-features` fails if tenant apps read `school.settings` or `school.features` (with allowlist).
- Tests: `apps/platform_runtime/tests/test_tenant_settings_lint.py`, `test_runtime_contract.py` (runtime has policy and blueprint; compilation order).
- Contract: No tenant view or service should import resolver internals or read School.settings for policy; use get_effective_policy or runtime.

## Versioning and audit

- PolicyBundle and TenantBlueprint changes should bump version or create snapshot where applicable.
- Apply/rollback actions should emit audit events (actor, before/after, reason); implement or document per control-plane flow.

## References

- apps/policies/resolver.py — get_effective_policy
- apps/platform_runtime/runtime_resolver.py — steps 4 (blueprint), 5 (policy)
- docs/PLATFORM_APPS_PUBLIC_API.md (policies section)
