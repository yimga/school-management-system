# Apps Audit Report: Gaps, RBAC, Security, Workflow & Code

**Date:** 2025-02-02  
**Scope:** All apps under `apps/` — bugs, RBAC compatibility, gaps, redundancy, security, workflow flaws, code issues.

---

## Executive Summary

- **RBAC:** Main compliance dashboard was accessible to any authenticated user; fixed to staff/ADMIN/LEADERSHIP only. Evals compliance dashboard and reporting views are correctly restricted.
- **Security:** No raw user input in SQL; `.extra()` usages use fixed expressions. Webhook is `@csrf_exempt` by design and protected by signature verification. Access control and document/thread access checks are in place where sampled.
- **Code:** Finance API field names and enums fixed (invoice_date→issued_date, payment_date→paid_at, Sum('amount')→Sum('total_amount')/status enums). Academics score distribution made DB-agnostic (removed `.extra()` with dialect-specific SQL).
- **Redundancy:** Two compliance dashboard implementations (main vs reporting) are intentional (main = high-level, reporting = detailed). Duplicate `is_admin_or_staff` in compliance exists; can be centralized.
- **Recommendations:** Add `GET /api/auth/profile/`; ensure all parent/guardian APIs filter by linked students; add tests for RBAC on sensitive views; document finance API base path.

---

## 1. Per-App Findings

### 1.1 Accounts

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| RBAC | Backend dashboard, RBAC dashboard, workflow center, import hub, clone/rollover, academic rules use `_is_admin_user` or `user_passes_test`. | OK | Keep; ensure any new admin views use same pattern. |
| Security | MFA middleware and `require_mfa_roles` in SiteSettings enforce MFA for configured roles. | OK | Document which roles are in `require_mfa_roles` by default. |
| Code | — | — | — |

**Verdict:** No critical gaps. Role checks are consistent for admin-only pages.

---

### 1.2 Compliance

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| RBAC | **FIXED:** Main dashboard at `/compliance/dashboard/` used only `@login_required`; any authenticated user could access. Now gated with `user_passes_test(_compliance_staff_required)` (staff / ADMIN / LEADERSHIP). | High → Fixed | Consider redirecting non-authorized users to a “no access” page instead of login if already logged in. |
| Redundancy | `ComplianceDashboardView` in `views.py` (main) and `views_dashboard.py` (reports sub-section). `is_admin_or_staff` defined in both `views_api.py` and `views_dashboard.py`. | Low | Centralize `is_admin_or_staff` in e.g. `apps/compliance/auth_utils.py` and reuse. |
| Security | Access control (IP/country) fails open on DB error; documented. API views use `@login_required` and ratelimit. | Low | Optional: make fail-open configurable for strict environments. |
| Workflow | Reporting sub-URLs under `/compliance/reports/` have their own dashboard with full metrics; main dashboard is overview. | OK | Document in user guide which URL to use when. |

**Verdict:** Main RBAC gap closed. Minor redundancy and documentation improvements recommended.

---

### 1.3 Finance

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| API bugs | **FIXED:** `api_views.py` used `invoice_date` (model uses `issued_date`), `payment_date` (model uses `paid_at__date`), `Sum('amount')` on Invoice (use `total_amount`), and string status filters instead of `Invoice.Status` enums. | High → Fixed | Add unit tests for finance API aggregations and filters. |
| SQL | `monthly_revenue` uses `.extra(select={'month': 'EXTRACT(month FROM paid_at)'})`. No user input; PostgreSQL-specific. | Low | If supporting SQLite for finance reports, use `TruncMonth` or conditional by backend. |
| Security | `invoice_receipt` is `@staff_member_required` and scoped by `profile=profile`. Webhook is `@csrf_exempt` with signature verification and logging. | OK | Keep; ensure webhook IP/signature checks are always on. |
| RBAC | Dashboard and sensitive actions use staff or role checks. Parent-facing invoice views (e.g. portal) must filter by guardian link. | OK | Verify all parent-facing finance endpoints filter by `StudentGuardian` / student link. |

**Verdict:** API bugs fixed. No remaining critical security or RBAC issues in sampled code.

---

### 1.4 Reports

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| SQL | `bi_services.py` uses `.extra(select={'month': "date_trunc('month', created_at)"})`. No user input; PostgreSQL-specific. | Low | If BI runs on SQLite, use Django’s `TruncMonth` or branch by DB. |
| RBAC | Publish term and report generation views check permissions and approved-grades settings. | OK | Keep; add tests for “reports_require_approved_grades_before_publish” and “reports_use_approved_grades_only”. |
| Workflow | Audit log entries created for publish term; evals–reports alignment documented. | OK | — |

**Verdict:** No critical issues. DB-specific SQL is the only minor point.

---

### 1.5 Evals

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| RBAC | `compliance_dashboard_view` and `extend_deadline_view` use `@staff_member_required` and `@role_required(User.Role.ADMIN, 'head_of_academics')`. Grade approval review checks `_user_can_review_grades`. | OK | — |
| Workflow | Grade approval flow and deadline extensions are consistent with single source for grading deadline (`SubjectAssignment.grading_deadline_at`). | OK | — |

**Verdict:** No gaps found in sampled views.

---

### 1.6 Portal

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| RBAC | Parent views use `@parent_portal_required` and `@role_required(User.Role.PARENT)`; teacher views use `@teacher_portal_required` and role checks. | OK | — |
| IDOR | `parent_child_results(student_id)` verifies `StudentGuardian` with `can_view_results=True` before showing results. | OK | — |
| Documents | `document_download` uses `document.can_view(request.user)`. Upload/delete require `permission_required("settings.manage")` and creator/superuser. | OK | — |

**Verdict:** Access control and ownership checks are in place.

---

### 1.7 Requests

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| RBAC | Dashboard and request detail use `@user_passes_test(_can_manage_requests)` (staff/superuser or role in allowed set). Requester cannot see other users’ requests via this view; only managers see list/detail. | OK | — |

**Verdict:** No issues.

---

### 1.8 Communication

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| RBAC | `group_detail` and `group_manage` check thread membership or staff; `group_join` checks department for department-scoped threads. | OK | — |

**Verdict:** Thread and join access properly restricted.

---

### 1.9 Academics (API)

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| Code | **FIXED:** `AssessmentResultsAPI` used `.extra()` with dialect-specific CASE (double-quoted literals break on SQLite). Replaced with `Case`/`When`/`Count` aggregation. | Medium → Fixed | — |
| RBAC | Assessment and attendance APIs use `IsTeacherOrAdmin` or role-scoped querysets (teacher sees only assigned classrooms). | OK | — |

**Verdict:** DB compatibility fix applied; RBAC consistent.

---

### 1.10 Analytics

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| RBAC | Views use `get_object_or_404` for year/term; ensure analytics dashboard and master sheet are restricted to staff/admin. | OK | Confirm all analytics URLs are behind staff or role decorator. |

**Verdict:** No critical issues identified.

---

### 1.11 Payroll

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| RBAC | Views use `get_object_or_404(PayrollRun, id=run_id)`; ensure payroll list/detail are staff-only or role-restricted. | OK | Verify decorators on all payroll views. |

**Verdict:** No critical issues identified.

---

### 1.12 API (apps/api)

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| Permissions | Uses DRF permission classes (`IsAdminUser`, `IsTeacherOrAdmin`, `IsBursar`, etc.) and role-based filtering. | OK | — |
| Gaps | Profile API: no `GET /api/auth/profile/`. Finance endpoints may live under finance app; not under `/api/` prefix. | Low | Add profile endpoint if needed; document finance API base path in API_COMPLETE_GUIDE.md. |
| Security | Schema access gated by `_is_schema_allowed`. Parent/guardian endpoints must filter by linked students. | OK | Audit all parent-facing ViewSets for StudentGuardian/link filtering. |

**Verdict:** Align with API_AUDIT_VS_GUIDE.md; add profile endpoint and document finance paths.

---

### 1.13 Siteconfig

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| SQL | `models.py` uses `cursor.execute` for optional column `video_background`; table name from `cls._meta.db_table` (not user input). | OK | — |
| Security | Preview/maintenance middlewares use request/user as documented. | OK | — |

**Verdict:** No critical issues.

---

### 1.14 Observability

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| SQL | Health checks use `cursor.execute("SELECT 1")` for DB liveness. | OK | — |

**Verdict:** No issues.

---

### 1.15 Automation

| Area | Finding | Severity | Recommendation |
|------|---------|----------|----------------|
| Integration | Tasks use `AutomationExecutionLog`; config from SiteSettings where applicable. | OK | — |

**Verdict:** No issues.

---

## 2. Cross-Cutting Summary

| Category | Status | Notes |
|----------|--------|------|
| **RBAC** | Fixed + OK | Compliance main dashboard fixed; others consistent. |
| **Security** | OK | No SQL injection from user input; webhook and access control reviewed. |
| **Workflow** | OK | Evals–reports, approval flow, and automation alignment in place. |
| **Redundancy** | Low | Duplicate `is_admin_or_staff` in compliance; two dashboard URLs intentional. |
| **Code / Bugs** | Fixed | Finance API fields/enums; academics score distribution DB-agnostic. |

---

## 3. Implemented Fixes (This Audit)

1. **Compliance:** Main `ComplianceDashboardView` in `apps/compliance/views.py` now has `@user_passes_test(_compliance_staff_required)` so only staff/ADMIN/LEADERSHIP can access `/compliance/dashboard/`.
2. **Academics API:** Replaced `.extra()` score buckets in `AssessmentResultsAPI` with `Case`/`When`/`Count` aggregation for SQLite/PostgreSQL compatibility.
3. **Finance API:** (Previously fixed) Corrected invoice/payment field names and status enums in `apps/finance/api_views.py`.

---

## 4. Recommended Next Steps (Implemented)

1. **Centralize compliance RBAC:** Done – `apps/compliance/auth_utils.py` defines `is_admin_or_staff`; used in `views.py`, `views_dashboard.py`, and `views_api.py`.
2. **API profile endpoint:** Done – `GET /api/auth/profile/` (ProfileView in `apps/api/entity_api.py`).
3. **Tests:** Done – compliance dashboard 403 for non-staff (`ComplianceDashboardRBACTestCase`); financial dashboard RBAC (`test_financial_dashboard_denies_parent`, `test_financial_dashboard_allows_bursar`); reports publish term staff-only and page load (`PublishTermRBACTestCase`).
4. **Documentation:** Done – `docs/API_AUDIT_VS_GUIDE.md` updated with finance API base path and parent-scoped endpoints; profile endpoint documented.
5. **Replace .extra():** Done – finance `api_views.py` uses `ExtractMonth('paid_at')`; reports `bi_services.py` uses `TruncMonth('created_at')` for DB-agnostic queries.

---

**Reference:** CODE_REVIEW_GAPS_REDUNDANCIES.md, API_AUDIT_VS_GUIDE.md, SECURITY_AUDIT_REPORT.md, AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md.
