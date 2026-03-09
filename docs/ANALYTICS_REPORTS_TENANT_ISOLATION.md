# Analytics and Reporting Tenant Isolation

**Purpose:** Ensure analytics, reporting, search, and export paths are scoped to the current tenant/school so no cross-tenant data is exposed.

## Analytics app

- **Views:** Run in tenant URLconf; `get_active_year_and_term()` and AcademicYear/Term/Classroom queries are in tenant schema. **strategic_report** now explicitly filters `StudentProfile` and `TeacherProfile` by `request.school` when set.
- **Export (CSV):** Analytics export uses the same view context (year_obj, term_obj, filters); evals and rankings are derived from tenant-scoped academic year/term. No cross-tenant export when request is tenant-scoped.
- **Tasks:** All analytics tasks (`send_deadline_reminders_task`, `compute_risk_factors_task`, `nightly_risk_factors_task`) run inside `_run_with_tenant_context(school_id=...)` (single school or iterate schools). ✓

## Reports app

- **BI services:** `ExecutiveReportingService` and `AdHocReportBuilder` accept optional `school_id`; `get_financial_summary`, `get_academic_summary`, `get_enrollment_trends` filter by `school_id` when provided. Cache keys use `_report_cache_prefix(school_id)`.
- **ScheduledReportRunner:** Runs in shared context; if `ScheduledReport` / report definitions are tenant-scoped (e.g. created per school), ensure the runner is invoked per school (e.g. from a task that runs with tenant context) or that models have school_id and runner filters by it. Document when adding scheduled reports.
- **ReportCard / views:** Report generation uses request/school context; preview and publish are tenant-scoped.

## Search and export (tenant-facing)

- **Search:** Tenant app search (e.g. student/guardian search in people, invoice search in finance) must use `request.school` or tenant context so results are school-scoped. Middleware and URLconf ensure tenant host has school set.
- **Export:** Any export from tenant list views (CSV/Excel) must use the same queryset as the list view (already school-filtered when view uses `request.school`).

## Status

- **Done:** strategic_report filters by school; analytics tasks run in tenant context; BI services support school_id; doc added.
- **Recommendation:** When adding new report or analytics endpoints, always pass or filter by school when the data is school-scoped.
