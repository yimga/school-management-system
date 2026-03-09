# Prompt 1 — Platform Transition Forensic Audit Report

**Date:** 2026-03-06  
**Scope:** Entire repository — single-school (Gilead) → multi-tenant global platform (RunMyCampus)  
**Non-negotiable:** All findings must be remediated.

---

## 1. Single-tenant assumption inventory

### 1.1 SiteSettings / global singleton (remediated with residual risk)

| Location | Finding | Status |
|----------|---------|--------|
| Tenant-facing apps | Tenant code must not call `SiteSettings.get_solo()`; use `get_effective_*` / `request.tenant_runtime`. | **Done:** Lint and test block new get_solo in tenant apps; allowlist: siteconfig/models, platform_runtime/helpers, policies/resolver, management commands, tests. |
| policies/resolver.py | Calls `SiteSettings.get_solo()` to build policy. | **Allowlisted** — control-plane policy build. |
| platform_runtime/helpers.py | Calls `get_solo()` inside helpers used by tenant code. | **Allowlisted** — canonical shim. |

### 1.2 Default school / “first” school assumptions

| File | Line / area | Finding | Status |
|------|-------------|--------|--------|
| apps/reports/views.py | 102–103 | _sample_student() no school filter. | **Done:** _sample_student(school=...), _build_preview_context(request=...) |
| apps/reports/services.py | ~775 | school_students without school filter. | **Done:** filter by student.school_id in annual_report_context |
| apps/reports/adhoc_runner.py | ~155–156 | When school_id is None, no school filter. | Documented: callers pass school_id in tenant context |
| apps/finance/views.py | 99 | ComplianceProfile.first() tenant scope. | URLconf/middleware scope; no change required |
| apps/academics/services.py | 20 | get_active_year_and_term(school=...). | Callers pass school in tenant context |

### 1.3 Gilead / single-school naming and branding

| File | Finding | Status |
|------|--------|--------|
| apps/schools/middleware.py | Comment example `/t/gilead/`. | Example only; no change |
| apps/accounts/context_processors.py | Comment `e.g. /t/gilead/`. | Example only; no change |
| apps/schools/error_views.py | "gilead" in name → slug (platform branding). | Intentional; no change |
| apps/accounts/management/commands/seed_render_users.py | ensure_gilead_admin. | Legacy seed; acceptable |
| apps/siteconfig/.../seed_admin_dashboard_palettes.py | Theme names "Gilead Warm Pink" etc. | **Done:** RunMyCampus Warm Pink, RunMyCampus Dark Neutral; slugs admin-runmycampus-* |
| apps/siteconfig/theme_palette_groups.py | Slug admin-gilead-warm-pink. | **Done:** admin-runmycampus-warm-pink |

### 1.4 Hardcoded region/currency/grading (tenant apps)

| File | Finding | Status |
|------|--------|--------|
| apps/finance (tasks, models, services) | CMR, XAF defaults/fallbacks. | **Done:** PLATFORM_DEFAULT_*; _default_currency(); get_platform_defaults() |
| apps/reports/services.py | REGION_CODE CMR, default_currency XAF, grading 0-20. | **Done:** get_platform_defaults() |
| apps/evals (help text remain) | 0-20, Cameroon in help text. | Model defaults use settings; help text cosmetic |
| apps/schools/signup_views.py | DEFAULT_SCHOOL_TIMEZONE Africa/Douala. | **Done:** get_platform_defaults()["timezone"] |
| apps/siteconfig/context_processors.py | REGION_CODE CMR, default_currency XAF. | **Done:** get_platform_defaults(use_db=False) |
| apps/schools/super_views.py | header_weather_country_code CMR. | **Done:** get_platform_defaults()["region_code"] |

### 1.5 Celery tasks without tenant context

| File | Finding |
|------|--------|
| apps/evals/tasks.py | `process_bulk_grades`: when `schema_name` is **None**, runs `_run_bulk_grades(...)` in **current schema** with no `_run_with_tenant_context` or `schema_context`. Callers must pass `schema_name` in multi-tenant; otherwise task can run unscoped. |

All other tenant-app tasks (finance, people, requests, analytics, communication) use `_run_with_tenant_context` or per-school iteration.

### 1.6 Single-tenant compatibility hook

| File | Finding | Status |
|------|--------|--------|
| apps/schools/middleware.py | _get_single_tenant_school(); SINGLE_TENANT=1. | **Done:** docs/SINGLE_TENANT_PRODUCTION.md — must be off in multi-tenant production |

---

## 2. Multi-tenant readiness score

**Score: 6.5 / 10** (post-remediation; was 5.5)

- **Strengths:** Tenant context in middleware/URLconf; schema-per-tenant/RLS; Celery tasks wrapped (except evals when schema_name omitted); get_solo blocked in tenant apps; control-plane decorators and template split; ORM/analytics audits and fixes.
- **Gaps (remediated):** Reports and evals task now school/tenant-scoped; hardcoding replaced with get_platform_defaults(); Gilead seeds/themes renamed to RunMyCampus; SINGLE_TENANT documented.

---

## 3. Refactor priority list (non-negotiable)

| Priority | Action |
|----------|--------|
| P0 | **Reports:** Add school filter to `_sample_student()` and all report code paths that query `StudentProfile` or tenant-scoped models; require `request.school` or explicit school_id where applicable. |
| P0 | **Evals task:** When `schema_name` is None, require `school_id` and run inside `_run_with_tenant_context(school_id=...)`, or document that callers must always pass schema_name in multi-tenant. |
| P1 | **Hardcoding:** Replace CMR/XAF/Africa/Douala/0-20 defaults in tenant apps with registry/env/blueprint (see lint_tenant_settings.py and SIDEBAR_DASHBOARD_REGISTRY_TARGET.md). |
| P2 | **Gilead naming:** Rename seed theme palettes and identifiers from "Gilead" to "RunMyCampus" or neutral in siteconfig seeds and theme_palette_groups (optional for branding). |
| P2 | **Document:** SINGLE_TENANT flag in middleware — document that it must be off for multi-tenant production. |

---

## 4. Evidence summary

- **Models:** Tenant models (people, finance, academics, evals, reports, etc.) have school FK or are in tenant schema; no single-school-only models left.
- **Views:** Tenant views run under tenant URLconf/middleware; most list views filter by request.school where applicable (see TENANT_ORM_AUDIT.md). Reports preview is the exception ( _sample_student ).
- **Settings/policies:** Policy resolver and runtime helpers centralize tenant behavior; tenant-facing code must not call get_solo() (enforced by lint).
- **Background jobs:** Finance, requests, accounts, people, analytics, communication tasks run with tenant context; evals process_bulk_grades needs schema_name or school_id when multi-tenant.

---

**P0 fixes applied (2026-03-06):**
- **Reports:** `_sample_student(school=...)` added; `_build_preview_context(..., request=...)` uses `_report_scope_school(request)` and passes school to `_sample_student`. `annual_report_context` in services.py now filters `school_students` by `student.school_id`.
- **Evals task:** `process_bulk_grades` accepts `school_id`; when `schema_name` or `school_id` is provided, runs inside `_run_with_tenant_context`; otherwise runs in current schema (single-tenant/test).

**Next:** Re-run this audit after further changes; proceed to Prompts 2–8 per pack order.
