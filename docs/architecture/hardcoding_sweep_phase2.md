# Phase 2 — Hardcoding sweep (Phase 3)

**Doc ref:** Section 24.1, 24.2; REMAINING_PHASES_EXECUTION_ORDER.md Phase 2.

## Scope

Remove remaining tenant/country hardcoding in **tenant-facing** views, templates, forms. Control-plane, signup, emis, setup flows may keep country/region by design.

## Done

- **Grading settings (tenant-facing):** Replaced hardcoded `GRADING_SCALE_CHOICES` (e.g. "Cameroon (0–20)") with `get_grading_scale_choices_for_school(school)`: choices from `GradingScaleConfig` for school’s region when available, else neutral labels ("Numeric 0–20", "Numeric 0–100", etc.) with no country names.
- **Evals/gradebook:** Already refactored in Phase 1 to use policy (grade_approval slice); no direct SiteSettings.
- **Admissions:** Already policy-driven (Phase 1 refactor).
- **Reports / context processor:** Already use policy for grading_scale and default_language when school is set.

## Acceptable by design

- **SiteSettings / RegionConfig defaults:** e.g. `get_default()` returning Cameroon, default_region choices, help_text mentioning CMR/XAF — these are platform/control-plane config, not tenant UX.
- **Admin / super:** Country/region in admin lists, region validation dashboard, signup/setup flows.
- **Registries / models:** Help text and examples (e.g. "e.g. CMR, USD") are documentation, not tenant behavior.

## Checklist

- [x] Tenant-facing grading form uses registry/policy-driven choices (no "Cameroon" in labels).
- [x] No country logic in tenant-facing evals, admissions, reports (policy only).
- [x] 24.1, 24.2 confirmed in RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md.
