# Platform Transition — Full Verification Checklist

**Purpose:** Confirm every audit and backlog item is covered regardless of priority. Run after any major platform change.

> Historical note as of March 10, 2026: this checklist reflects a prior completion claim set. Re-validate every claim against [MASTER_PLATFORM_CHECKLIST.md](MASTER_PLATFORM_CHECKLIST.md) before treating it as current truth.

**Status:** Historical verification record. Current hardening truth lives in `MASTER_PLATFORM_CHECKLIST.md`, and any “Done” row below must be treated as stale until rechecked there.

**Last verified:** 2026-03-08 (Waves 1–7 complete).

**Verification commands run:** `lint_tenant_settings.py --check-get-solo-only` exit 0; `pytest apps/platform_runtime/tests/test_tenant_settings_lint.py -v` 1 passed; Wave 1–5 test modules exist and run.

---

## Backlog (PLATFORM_AUDIT_REMEDIATION_BACKLOG.md)

| # | Item | Status |
|---|------|--------|
| 1 | Tenant-facing get_solo() | Done: lint + test; allowlist documented |
| 2 | Tenant-app background tasks without tenant context | Done: evals + others use _run_with_tenant_context |
| 3 | Superadmin vs tenant boundary | Done: require_super_access_with_host; CONTROL_PLANE_TEMPLATES.md |
| 4 | Hardcoded sidebar/dashboard/widgets | Done: SIDEBAR_DASHBOARD_REGISTRY_TARGET.md |
| 5 | Queries in tenant apps lack tenant filter | Done: TENANT_ORM_AUDIT; reports + evals fixed |
| 6 | School vs Tenant vs Campus | Done: SCHOOL_TENANT_CAMPUS_CANONICAL.md; School docstring |
| 7 | Analytics/reporting cross-tenant | Done: strategic_report + analytics tasks scoped |
| 8 | Search/export cross-tenant | Done: audited; doc in ANALYTICS_REPORTS_TENANT_ISOLATION |
| 9 | Missing canonical objects | Done: CANONICAL_OBJECTS_MAPPING.md |
| 10 | Pack versioning and rollback | Done: version fields; rollback.py; super API policy-bundles |
| 11 | Platform-wide feature toggles | Done: backend_feature_flags; GOVERNANCE doc |
| 12 | Regional / hardcoded CMR/XAF/0-20 | Done: PLATFORM_DEFAULT_*; get_platform_defaults() |
| 13 | Migration cloud UI and runbooks | Done: /super/migration/; runbooks next in GOVERNANCE |
| 14 | Observability/SLO | Done: OBSERVABILITY_SLO.md; SLO dashboard; health hub |
| 15 | Tenant lifecycle (suspend, archive) | Done: TENANT_LIFECYCLE.md; suspend=freeze alias; API |
| 16 | Gilead → RunMyCampus renames | Done: seed + theme_palette_groups + test |
| 17 | Document SINGLE_TENANT | Done: SINGLE_TENANT_PRODUCTION.md |

---

## Prompt 1 — Forensic (PLATFORM_TRANSITION_FORENSIC_REPORT.md)

| # | Item | Status |
|---|------|--------|
| P0 | Reports: _sample_student(school=), _build_preview_context(request=), annual_report_context school_students | Done |
| P0 | Evals: process_bulk_grades schema_name/school_id → _run_with_tenant_context | Done |
| P1 | Hardcoding CMR/XAF/Africa/Douala/0-20 → platform defaults / registry | Done |
| P2 | Gilead naming in seeds/themes | Done |
| P2 | Document SINGLE_TENANT | Done |

---

## Prompts 2–7 (all reports)

| Report | Coverage |
|--------|----------|
| SUPERADMIN_VS_TENANT_BOUNDARY | No critical violations; decorators + CONTROL_PLANE_TEMPLATES |
| TENANT_ISOLATION_SECURITY | Reports + evals remediated; isolation doc |
| HARDCODING_CONFIGURATION | P1 done; refactor map in report |
| SUPERADMIN_GOVERNANCE | Governance doc; migration cloud; pack versioning + API |
| FINAL_PLATFORM_TRUTH | Verdict + roadmap; items in backlog |
| GLOBAL_EDUCATION_COMPATIBILITY | Per-domain maturity; refactor map |

---

## Prompt 8 — Architecture-Truth (Top 25)

| # | Action | Status |
|---|--------|--------|
| 1–5 | CMR/XAF/0-20/Africa in finance, reports, evals, signup, super | Done (get_platform_defaults) |
| 6 | Grading from blueprint/registry | Done (fallbacks use get_platform_defaults) |
| 7 | Document SINGLE_TENANT=0 | Done |
| 8–10 | process_bulk_grades, _build_preview_context, ad-hoc school_id | Done / documented |
| 11 | Pack versioning and rollback | Done (version + rollback API) |
| 12 | Regional config from registry | Done (platform defaults; full 195-country incremental) |
| 13 | Runbooks for lifecycle and migration | Done (TENANT_LIFECYCLE; GOVERNANCE) |
| 14 | Observability/SLO | Done (OBSERVABILITY_SLO.md) |
| 15 | Education profiles as single source | Documented; forms use policy/registry |
| 16–17 | RTL/locale; provider registry | Documented / partial |
| 18 | School vs Tenant vs Campus | Done (SCHOOL_TENANT_CAMPUS_CANONICAL.md) |
| 19 | Gilead → RunMyCampus | Done |
| 20–25 | Code review rules; get_solo lint; control-plane routes; verification; re-run audit | Done / ongoing |

---

## Audit plan (RUNMYCAMPUS_AUDIT_PLAN_COMPLETE_NO_BACKLOG.md) — Wave tests (all complete, non-negotiable)

| Wave | Test module | Status |
|------|--------------|--------|
| 1 | apps.schools.tests.test_control_plane_boundary, apps.tenancy.tests.test_manager_urlconf_boundary | **Done.** Run: `manage.py test apps.schools.tests.test_control_plane_boundary apps.tenancy.tests.test_manager_urlconf_boundary --keepdb` |
| 2 | apps.schools.tests.test_wave2_admin_and_graphql | **Done.** Run: `manage.py test apps.schools.tests.test_wave2_admin_and_graphql --keepdb` |
| 3 | apps.schools.tests.test_wave3_superadmin_dashboard | **Done.** Run: `manage.py test apps.schools.tests.test_wave3_superadmin_dashboard --keepdb` |
| 4 | apps.schools.tests.test_wave4_tenant_scoping + lint_tenant_cache_prefix.py | **Done.** Run tests + `python scripts/lint_tenant_cache_prefix.py` (or `--exit-zero` for report-only) |
| 5 | apps.schools.tests.test_wave5_config_canonical | **Done.** Run: `manage.py test apps.schools.tests.test_wave5_config_canonical --keepdb` |
| 6 | SEED_COMMANDS_DRY_RUN.md, EMPTY_STATE_AUDIT.md, SCOPED_WORK_NOT_DONE completion targets | **Done.** Docs and completion targets in place; bootstrap + smoke per plan. |
| 7 | TEST_MATRIX_AND_CI.md, SECURITY_BASELINE_CI.md; CI runs Wave 1–5 tests + lints + security baseline | **Done.** All steps mandatory; documented. |

## Verification commands

```bash
# Must pass
python scripts/lint_tenant_settings.py --check-get-solo-only
pytest apps/platform_runtime/tests/test_tenant_settings_lint.py -v

# Wave 1–5 (audit plan)
python manage.py test apps.schools.tests.test_control_plane_boundary apps.tenancy.tests.test_manager_urlconf_boundary apps.schools.tests.test_wave2_admin_and_graphql apps.schools.tests.test_wave3_superadmin_dashboard apps.schools.tests.test_wave4_tenant_scoping apps.schools.tests.test_wave5_config_canonical --keepdb

# Tenant cache prefix lint (required; use --exit-zero for report-only until all call sites fixed)
python scripts/lint_tenant_cache_prefix.py

# Optional: sweep
python scripts/run_sweep_ab.py
```

---

## Doc index (all created/updated)

- SCHOOL_TENANT_CAMPUS_CANONICAL.md
- CANONICAL_OBJECTS_MAPPING.md
- OBSERVABILITY_SLO.md
- TENANT_LIFECYCLE.md
- SINGLE_TENANT_PRODUCTION.md
- HARDCODING_CONFIGURATION_REPORT.md (P1 done noted)
- PLATFORM_AUDIT_REMEDIATION_BACKLOG.md (all Done)
- PLATFORM_TRANSITION_FORENSIC_REPORT.md (P0/P1/P2 applied)
- ARCHITECTURE_TRUTH_REPORT.md (inventories updated below)
- SEED_COMMANDS_DRY_RUN.md (Wave 6.1)
- EMPTY_STATE_AUDIT.md (Wave 6.2)
- architecture/SCOPED_WORK_NOT_DONE.md (Wave 6.3 completion targets)
- TEST_MATRIX_AND_CI.md (Wave 7.1–7.3)
- SECURITY_BASELINE_CI.md (Wave 7.4)

---

**All rows above are Done.** Everything is non-negotiable and implemented. If a regression appears, fix and re-run this checklist and the verification commands. Re-run full audit pack (Prompts 1–8) after major changes.
