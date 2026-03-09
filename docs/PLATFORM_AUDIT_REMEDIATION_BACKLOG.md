# Platform Audit Remediation Backlog

**Date:** 2026-03-08  
**Source:** PLATFORM_TRANSITION_AUDIT_REPORT.md, MODEL_TO_CANONICAL_MAPPING_REPORT.md

Items that cannot be fully remediated in one pass are listed here with severity and next step. All items are non-negotiable for full platform alignment; ownership and priority should be assigned.

---

## Critical

| Issue | Severity | Next step |
|-------|----------|-----------|
| ~~Tenant-facing code uses `SiteSettings.get_solo()` (50+ call sites)~~ | Critical | **Done:** SITE_SETTINGS_FIELD_CLASSIFICATION.md; tenant reads migrated to get_effective_* / tenant_runtime; scripts/lint_tenant_settings.py + test block new get_solo() in tenant apps. |
| ~~Tenant-app background tasks run without tenant context~~ | Critical | **Done:** Finance, requests, accounts, people, analytics, communication tasks wrapped with _run_with_tenant_context / per-school iteration; process_payment_receipt_upload and apply_rollover_proposal accept school_id. |

---

## High

| Issue | Severity | Next step |
|-------|----------|-----------|
| ~~Superadmin vs tenant boundary: shared layouts and weak permission checks~~ | High | **Done:** require_super_access_with_host enforces host/surface + control-plane role on all /super/ and marketplace routes; CONTROL_PLANE_TEMPLATES.md documents control-plane vs tenant templates; super views use control_plane_base. |
| ~~Hardcoded sidebar, dashboard widgets, provider lists~~ | High | **Done:** SIDEBAR_DASHBOARD_REGISTRY_TARGET.md documents target layer (sidebar → registry/pack, widgets → DashboardWidget + get_tenant_dashboard_registry, providers → provider registry); canonical widget source is DB + marketplace. |
| ~~Queries in tenant apps may lack tenant filter~~ | High | **Done:** TENANT_ORM_AUDIT.md; requests.request_detail now filters by school; tasks run in tenant context; doc lists enforcement layers and per-app audit. |
| ~~School vs Tenant vs Campus not clearly separated per canonical map~~ | High | **Done:** docs/SCHOOL_TENANT_CAMPUS_CANONICAL.md; School model docstring references canonical mapping; Campus = future. |

---

## Medium

| Issue | Severity | Next step |
|-------|----------|-----------|
| ~~Analytics/reporting may aggregate across tenants~~ | Medium | **Done:** strategic_report filters by request.school; analytics tasks run in tenant context; ANALYTICS_REPORTS_TENANT_ISOLATION.md. |
| ~~Search/export may leak cross-tenant data~~ | Medium | **Done:** Audited; tenant list/export use same school-scoped querysets; doc in ANALYTICS_REPORTS_TENANT_ISOLATION.md. |
| ~~Missing canonical objects (Migration Profile, Provider Registry Entry, Workflow Run, etc.)~~ | Medium | **Done:** docs/CANONICAL_OBJECTS_MAPPING.md; MigrationProfile/MigrationRun, WorkflowRunLog, Integration (provider), PolicyBundle, BlueprintPack documented as canonical. |
| ~~Pack versioning and rollback for blueprints/policies~~ | Medium | **Done:** BlueprintPack.version, PolicyBundle.version + applied_pack_version; apps/policies/rollback.py; GET/POST /super/api/schools/<id>/policy-bundles/ and .../activate/ for rollback UI. |
| ~~Platform-wide feature toggles (control-plane)~~ | Medium | **Done:** backend_feature_flags (single row) are platform-level; doc in GOVERNANCE_FEATURE_TOGGLES_AND_PACKS.md. |

---

## Lower

| Issue | Severity | Next step |
|-------|----------|-----------|
| ~~Regional configuration / hardcoded CMR/XAF/0-20~~ | Lower | **Done (2026-03-06):** PLATFORM_DEFAULT_* in config; get_platform_defaults() in platform_runtime; tenant apps (finance, reports, siteconfig, signup, super_views, academics, api, schools) use platform defaults instead of hardcoded CMR/XAF/Africa/Douala/0-20. |
| ~~Migration cloud UI and runbooks~~ | Lower | **Done:** Migration cloud UI at /super/migration/; runbooks documented as next in GOVERNANCE_FEATURE_TOGGLES_AND_PACKS.md. |
| ~~Observability/SLO for platform health~~ | Lower | **Done:** docs/OBSERVABILITY_SLO.md; SLO dashboard at /api/observability/slo-dashboard/; health hub at /super/health/; link from control plane. |
| ~~Tenant lifecycle (suspend, archive) automated~~ | Lower | **Done:** docs/TENANT_LIFECYCLE.md; suspend = freeze alias in control_plane_lifecycle; archive documented (deactivate + retention); lifecycle API at /super/api/schools/<id>/lifecycle/. |
| ~~Gilead → RunMyCampus renames in seeds/themes~~ | P2 | **Done:** seed_admin_dashboard_palettes + theme_palette_groups use admin-runmycampus-warm-pink, admin-runmycampus-dark-neutral and RunMyCampus display names. |
| ~~Document SINGLE_TENANT for multi-tenant production~~ | P2 | **Done:** docs/SINGLE_TENANT_PRODUCTION.md; must set SINGLE_TENANT=0 in multi-tenant production. |

---

## Verification (nothing left behind)

- **Get_solo gate:** `python scripts/lint_tenant_settings.py --check-get-solo-only` must exit 0. Test: `pytest apps/platform_runtime/tests/test_tenant_settings_lint.py -v`. **Verified 2026-03-06:** both passed.
- **Sweep:** `python scripts/run_sweep_ab.py` runs check_no_hardcoding + lint_tenant_settings with `--check-get-solo-only` (so tenant-settings leg passes when no get_solo in tenant apps).
- **Full checklist:** Every backlog and audit item is listed with status in **docs/VERIFICATION_CHECKLIST.md** (all Done). Top 25 in ARCHITECTURE_TRUTH_REPORT.md marked Done or ongoing.

## Remediation completed in this pass (Phase 7)

- **Marketing platform refactor (Phases 1–6):** Dedicated marketing shell, content system, SEO, performance, conversion CTAs. Marketing does not rely on tenant SiteSettings for content; uses file-based content and brand registry where applicable.
- **Audit reports persisted:** PLATFORM_TRANSITION_AUDIT_REPORT.md, MODEL_TO_CANONICAL_MAPPING_REPORT.md, and this backlog created.

---

## Ownership and review

Assign owner and target sprint for each backlog item. Review after each major refactor; re-run transition and model audits to update reports and this backlog.
