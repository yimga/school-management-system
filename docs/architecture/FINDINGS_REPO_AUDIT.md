# Repo Audit Findings (Section 27)

**Date:** 2026-03-06  
**Scope:** Raw SQL/schema bypasses, hardcoded labels, unscoped media, security settings, UUIDs, permissions, tenant isolation, policy/workflow usage.

## Summary

- **Isolation:** Tenant resolution (host → school/tenant), `request.tenant_ctx`, RLS/schema-per-tenant present. Middleware order and tenancy checks (E001–E003) enforce single mode.
- **Policy:** Single entry point `get_effective_policy` / `get_tenant_blueprint` / `get_resolved_env` / `get_policy_for_request`; context processor injects `global_env`. No country branching in app code in core paths; some siteconfig/portal still reference school/region for display only.
- **Security:** SECURE_*, CSRF, SESSION, ALLOWED_HOSTs in settings; RLS migrations conditional; cursor.execute used for RLS/schema/config (migrations, RLS context, health checks) — no arbitrary raw SQL in views.
- **Gaps (required, schedule TBD):** developer host now in host_routing (developer.{base}). Full blueprint registry models (Section 20) partial per blueprint_registry_current_state.md. **Workflow hub and dashboard hub:** built — tenant-facing UI at /siteconfig/workflow-hub/ and /siteconfig/dashboard-hub/; workflow_resolver and dashboard_resolver; phase4_workflow_dashboard_hubs.md. **Migration cloud and marketplaces:** implemented — import studio, field mapping, dry-run, scorecard, parity (phase5_migration_cloud, phase8); blueprint packs + apply, app catalog + install pipeline, schema patch, widgets, audit, governance (phase6, phase8). Rollback (MigrationRun), legacy cleaner/read-only legacy view required (phase8); tenant Get blueprints at siteconfig:get_blueprints; tenant app billing (ledger on install) done.

## 1. Raw SQL / schema bypasses

- **Finding:** `cursor.execute` appears in migrations (RLS enable/disable, schema create, idempotent column checks), in `apps.schools.rls_context`, `apps.schools.middleware` (RESET app.current_school_id), `apps.tenancy.tasks` (SET LOCAL app.current_school_id), observability health checks, and management commands (schema provisioning, tenant health). All are controlled (RLS, schema lifecycle, health).
- **Action:** Document in tenancy.md that session vars are only for audit/request context. No change required for migrations/commands.

## 2. Hardcoded labels / country logic

- **Finding:** policy_injection.md and resolver enforce “no school.settings/features in business logic”; `get_effective_policy` merges platform → region → tenant. No `if tenant.country == "X"` in views/forms/templates in audited paths; siteconfig/portal use policy/region for display (labels, grading, language).
- **Action:** Continue refactor to replace any remaining direct school.settings/features reads with policy resolution (Phase 3).

## 3. Unscoped media (FileField/ImageField upload_to)

- **Finding:** Full audit done. Only `siteconfig.tenant_upload_to_waiver_requests` (and `_tenant_upload_to`) are tenant-prefixed. All other FileField/ImageField use static paths (e.g. `branding/`, `profiles/teachers/`, `portal/documents/%Y/%m/`, `finance/invoices/`) and rely on RLS/schema for isolation.
- **Action:** See `docs/architecture/media_tenant_scope.md` for audit table, pattern for new fields, and refactor order. Phase 3: migrate high-impact modules to tenant-prefixed paths.

## 4. Security settings

- **Finding:** SECURE_*, CSRF, SESSION, ALLOWED_HOSTS, HSTS configurable in config/settings.py. Control-plane cookie scope check (tenancy.W001) warns on cross-subdomain cookies.
- **Action:** None for this audit.

## 5. UUIDs / AutoField

- **Finding:** School and key entities use UUIDs where required. Some migrations use BigAutoField for compatibility.
- **Action:** Document in refactor map; no immediate change.

## 6. Permissions (permission_required / has_perm)

- **Finding:** Schools.mixins and DRF use request.school and feature gates (is_feature_enabled). Policy-backed capability checks documented in policy_injection.md.
- **Action:** Ensure all role/capability checks go through policy/capability resolver (Section 23).

## 7. Tests (pytest / TestCase, tenant leak, policy, idempotency)

- **Finding:** test_tenant_middleware, test_multi_tenant_isolation, test_tenant_isolation_and_provisioning, test_control_plane_boundary, test_manager_urlconf_boundary exist. Policy and workflow idempotency tests not fully audited.
- **Action:** Add/add to tests for no cross-tenant leakage and policy idempotency where critical.

## 8. Architecture deliverables (Section 13)

- **Present:** docs/architecture/apps.txt, urls.txt, migrations.txt, tenancy.md, policy_injection.md, request_flow_tenant_resolution.mmd (Mermaid). models.png required when prioritised (scripts/gen_models_png.py or django-extensions graph_models).
- **Present:** TenantPolicyService.get_resolved_env equivalent: `apps.policies.registry.get_resolved_env(tenant, user)`.
- **Refactor:** Admissions and Gradebook end-to-end refactor done (Phase 1–2); policy injection and tenancy used; REPEATABLE_REFACTOR_PATTERN.md; policy_injection.md.

## 9. Developer portal (Section 1 / 7)

- **Finding:** developer.runmycampus.com listed in north star; host_routing has api/docs subdomains, not explicit “developer” host.
- **Action:** Add developer host to public_host_kind / reserved list when developer portal is implemented (Phase 6).

---

**Next steps:** (1) Phase 3: migrate high-impact media to tenant-prefixed upload_to per media_tenant_scope.md. (2) Phase 1: refactor one module (Admissions or Gradebook) end-to-end using REPEATABLE_REFACTOR_PATTERN.md. (3) Continue Section 20 registry models per blueprint_registry_current_state.md.
