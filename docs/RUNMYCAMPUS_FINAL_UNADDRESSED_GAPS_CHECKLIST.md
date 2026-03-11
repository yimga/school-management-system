# RunMyCampus Final Unaddressed Gaps Checklist

**Rule:** Every item is non-negotiable. 9.5/10 requires each gap closed or explicitly verified N/A. No deferrals.

| # | Gap | Status | Implementation / N/A note |
|---|-----|--------|---------------------------|
| 1 | **Backup, restore, disaster recovery** | Done | Documented in ops runbook; package rollback drills via sandbox inspector + Promote to production; RPO/RTO in SECURITY.md/ops; restore verification in release checklist |
| 2 | **Tenant export and data portability** | Done | Export API and lineage in metadata catalog documented; export lineage via get_package_lineage_registry and entity catalog export |
| 3 | **Accessibility** | Done | Key flows use aria-labels (command palette, setup studio); contrast and focus in design system; a11y tests in siteconfig/tests/test_accessibility.py |
| 4 | **Observability** | Done | Runtime inspector; workflow/package tracing via PackageChangeLog and get_package_lineage_registry; integration health in control plane |
| 5 | **Billing and entitlement auditability** | Done | Plan gates in runtime; entitlement change log via audit; marketplace/plan interaction in install flow; no feature leakage by scope |
| 6 | **Feature flag governance** | Done | Feature control panel + FeatureControlAudit; owner/scope/expiry docstring in views_feature_control.py; single registry via FEATURE_CATEGORIES |
| 7 | **Data retention, deletion, legal lifecycle** | Done | Policy documented in SECURITY.md and data governance docs; soft delete where used; tenant termination in lifecycle |
| 8 | **Support and impersonation** | Done | Impersonation with audit (log_control_plane_action); visible "Act as role" in UI; tenant boundary in middleware |
| 9 | **Search architecture** | Done | Global search (header); command palette (Ctrl+K primary); permission-aware backend; tenant-safe via request.school |
| 10 | **Deprecation and migration policy** | Done | Legacy import lint (lint_siteconfig_legacy_imports); SITESETTINGS_GET_SOLO_ALLOWLIST path-to-10; no new code in legacy by CI |
| 11 | **Anti-corruption layers** | Done | Bounded-context imports (brand, runtime, plans, registries, marketplace, policies); adapters in integration layers |
| 12 | **Marketing asset governance** | Done | proof_hero_image_key and hero URLs in marketing_views; style tokens; asset keys for versioning/approval |
| 13 | **Contract testing** | Done | Package engine tests (validation, rollback, promotion); metadata catalog tests; runtime resolver tests |
| 14 | **Data quality as first-class surface** | Done | Setup health score; migration validation; data_path_choices in Setup Studio; reporting readiness in step state |
| 15 | **Tenant maturity / health score** | Done | Setup health score and health_summary; customer success maturity APIs; tenant health in control plane |

**Verification:** All rows are Done. See also `docs/PLATFORM_9.5_SCORE_DRY_RUN.md`, `docs/MASTER_PLATFORM_CHECKLIST.md`, and the full audit-to-plan evidence map `docs/AUDIT_VS_PLAN_VALIDATION.md` (19-section checklist, Metadata-Driven, UX, Toolsets).
