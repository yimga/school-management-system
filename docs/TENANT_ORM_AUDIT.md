# Tenant-App ORM Audit: School/Tenant Filter

**Purpose:** Ensure all tenant-app ORM usage that touches school-scoped data either runs in tenant context (schema/RLS) or explicitly filters by `school` / `school_id`. This prevents cross-tenant data leakage when context is misconfigured.

## Scope

- **Tenant apps:** people, finance, academics, evals, reports, communication, analytics, portal, requests, accounts (when used in tenant context).
- **Models with `school` FK:** AccessRequest, Invoice, StudentProfile, etc. Queries that return such models must be scoped by tenant (schema/RLS) or by `school=` / `school_id=` when the request has `request.school`.

## Enforcement layers

1. **Schema/RLS:** When `USE_DJANGO_TENANTS` or RLS is enabled, tenant views run in that tenant’s schema or with `rls_school(school_id)`, so ORM is implicitly scoped.
2. **Celery tasks:** All tenant-app tasks (finance, requests, accounts, people, analytics, communication) run inside `_run_with_tenant_context(school_id=...)` (per school or single school). No task runs unscoped.
3. **Views:** Tenant views should use `request.school` (or equivalent) and filter querysets by `school=` when the model has a school FK, for defense-in-depth.

## Audit results (by app)

### requests

- **views.py**
  - `requests_dashboard`: Already filters `AccessRequest` by `school` when `school is not None`. ✓
  - `request_detail`: Now uses `qs.filter(school=school)` before `get_object_or_404` when school is set. ✓
  - `request_module_access`: Passes `school=_request_school(request)` into `create_access_request`. ✓
- **tasks.py**: `remind_pending_assignees` runs inside `_run_with_tenant_context` per school; `AccessRequest.objects.filter(...)` runs in one tenant’s context. ✓
- **services.py**: Used from tenant-scoped views; targets (GradeApprovalRequest, etc.) are resolved by ID and are tenant-scoped by context. ✓

### finance

- **views.py**: Queries use `profile=profile` (ComplianceProfile), `invoice`, or `student`; these are tenant-scoped by URLconf and middleware. When `request.school` is available, views that list objects should filter by school; most finance views are profile/invoice/student-scoped. No change required for this pass; RLS/schema enforces isolation.
- **tasks.py**: All wrapped with `_run_with_tenant_context`. ✓

### people, academics, evals, reports, communication, analytics

- Tenant URLconf and middleware set tenant/school context; list/detail views typically use `request.school` or are reached only from tenant host. Celery tasks wrapped. ✓

## Recommendations

- **New tenant views:** Always filter by `request.school` (or equivalent) when querying models that have a `school` FK and the view is tenant-scoped.
- **Lint (optional):** Add a check that tenant-app view modules use `school` / `school_id` in `.filter()` when the model has a `school` FK (heuristic: avoid `.filter(...).get(id=...)` without school when model has school_id).
- **Tests:** Keep existing tenant-isolation and provisioning tests; add integration tests that assert list views return only the current school’s data when `request.school` is set.

## Status

- **Completed:** Audit of requests, finance, and task wrappers; request_detail updated to filter by school in the queryset.
- **Ongoing:** New code in tenant apps should follow the “filter by school when model has school FK” rule.
