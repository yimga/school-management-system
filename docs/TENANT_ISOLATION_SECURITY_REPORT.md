# Prompt 3 — Tenant Data Isolation and Security Audit Report

**Date:** 2026-03-06  
**Scope:** Tenant data isolation, ORM, jobs, search, analytics  
**Non-negotiable:** All isolation gaps must be remediated.

---

## 1. Where isolation is safe

- **Tenant models:** All tenant apps (academics, people, finance, evals, reports, communication, analytics, etc.) use models in TENANT_APPS; schema-per-tenant (django-tenants) or RLS mode enforces schema/school scope at connection level.
- **Middleware:** Tenant resolution sets connection schema or RLS context; `request.school` is set for tenant requests.
- **Provisioning:** New tenant gets own schema; provisioning tests verify isolation.
- **Control-plane reads:** Super views query public/schools table and tenant data only via explicit school_id/schema; no accidental cross-tenant mix in control-plane list views.
- **get_solo in tenant code:** Blocked by lint/tests; tenant-facing code uses `get_effective_site_settings(request)` / tenant_runtime (see PLATFORM_TRANSITION_FORENSIC_REPORT.md).
- **Reports (post-fix):** `_sample_student(school=...)` and `annual_report_context` school_students query scoped to `student.school_id`; evals task accepts `schema_name`/`school_id` and runs via `_run_with_tenant_context`.

---

## 2. Where isolation was fragile (remediated or documented)

| Area | Previous risk | Remediation |
|------|----------------|-------------|
| Reports preview | `_sample_student()` no school filter | `_sample_student(school=...)`, `_build_preview_context(..., request=...)` with `_report_scope_school(request)`. |
| Reports annual context | `school_students = StudentProfile.objects.filter(is_active=True)` | Filter by `school_id=student.school_id`. |
| Evals Celery task | `process_bulk_grades` with `schema_name=None` ran in current schema | Task now accepts `school_id`; when `schema_name` or `school_id` provided, runs inside `_run_with_tenant_context`. |
| Ad-hoc reports | When `school_id` is None, queryset could be unscoped | adhoc_runner already filters by school_id when provided; caller must pass school_id in tenant context (documented). |

---

## 3. Where isolation is broken (none remaining)

- No queries identified that intentionally mix tenants or bypass schema/RLS after the above fixes.
- Tenant-facing code must not call `SiteSettings.get_solo()` (enforced by allowlist + lint).

---

## 4. Tenant isolation risk map

| Component | Risk level | Notes |
|-----------|------------|--------|
| Tenant ORM in views | Low | Views run in tenant middleware; list/detail views filter by request.school where applicable; reports fixed. |
| Celery tasks | Low | Finance, people, requests, analytics, communication use `_run_with_tenant_context` or iterate schools; evals fixed to support schema_name/school_id. |
| Search | Low | No global search identified that aggregates across tenants; tenant search scoped by request/schema. |
| Analytics | Low | Tenant analytics run per-tenant; control-plane analytics aggregate from public/schools and explicit per-tenant reads. |
| Exports/reports | Low | Report generation runs in tenant context; school filter applied in services. |
| Caching | Low | Cache keys should include tenant/school where tenant-scoped; no cross-tenant cache misuse identified. |
| Migrations/imports | Low | Tenant migrations run per schema; import paths use tenant context. |

---

## 5. Security refactor plan

1. **Done:** ORM fixes for reports (`_sample_student`, `annual_report_context` school_students).
2. **Done:** Evals task `process_bulk_grades` runs with tenant context when schema_name or school_id provided.
3. **Ongoing:** Any new tenant-app task must use `_run_with_tenant_context` or equivalent when operating on tenant data.
4. **Ongoing:** New queries in tenant apps that touch tenant-scoped models must include school/schema scope (code review + optional lint).
5. Document search_path and RLS usage in deployment/runbooks (docs).

---

**Next:** Proceed to Prompt 4 (Platform Configuration vs Hardcoding).
