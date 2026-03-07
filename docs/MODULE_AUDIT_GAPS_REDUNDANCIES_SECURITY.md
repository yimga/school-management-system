# Module-by-Module Audit: Gaps, Redundancies, Security & Workflow

**Date:** 2025-02-02  
**Scope:** All apps under `apps/` — gaps, redundancies, security issues, workflow issues, and suggestions.

---

## Executive Summary

| Category | Status | Notes |
|----------|--------|--------|
| **Bugs fixed this pass** | 2 | Portal: `guardian`→`guardian_user` in signature view; People: `user`→`guardian_user` + enum in backend student create. |
| **Security** | OK / documented | CSRF-exempt webhook by design; raw SQL in migrations/siteconfig/observability only; access control fail-open documented. |
| **Redundancy** | Low | Duplicate admin-check helpers across accounts vs compliance; report handlers code-only. |
| **Gaps** | Documented | Automation underused; no admin UI for report handlers; permission style mixed. |
| **Workflow** | OK | Evals–reports, guardian scoping, request management consistent. |

---

## 1. Per-Module Findings

### 1.1 Accounts

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | Backend dashboard, RBAC dashboard, workflow center, import hub, certification use `_is_admin_user` or `user_passes_test`. | OK | Keep; ensure new admin views use same pattern. |
| **Redundancy** | `_is_admin_user` in `views.py` and duplicate in `views_certification.py`; compliance uses `is_admin_or_staff` in its own app. | Low | Consider a shared `accounts.auth_utils` or `core.decorators` with one canonical “admin/staff” check used by accounts + compliance (and optionally others). |
| **Security** | MFA middleware and `require_mfa_roles` in SiteSettings. | OK | Document which roles are in `require_mfa_roles` by default. |
| **Workflow** | Claim-invite, profile, notifications, workflow center are coherent. | OK | — |

**Verdict:** No critical gaps. Optional: centralize admin-check logic.

---

### 1.2 Compliance

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | Main dashboard and reporting views use `is_admin_or_staff` from `auth_utils.py`. | OK (fixed earlier) | Consider redirecting already-logged-in non-authorized users to a “no access” page instead of login. |
| **Redundancy** | Two dashboard entry points (main vs reports) are intentional (overview vs detailed). `is_admin_or_staff` is now centralized in `auth_utils.py`. | OK | — |
| **Security** | Access control (IP/country) fails open on DB error; documented in code. API views use `@login_required` and ratelimit. | Low | Optional: make fail-open configurable for strict environments. |
| **Workflow** | Reporting sub-URLs under `/compliance/reports/` have full metrics; main dashboard is overview. | OK | Document in user guide which URL to use when. |

**Verdict:** RBAC fixed; minor redundancy and documentation improvements only.

---

### 1.3 Finance

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **Security** | `payment_provider_webhook` is `@csrf_exempt` by design; comment documents IP whitelist, HMAC, rate limiting, idempotency. | OK | Ensure webhook validator and WebhookLog are always enabled; consider automated tests for webhook security path. |
| **RBAC** | Dashboard and sensitive actions use staff/role checks. Parent-facing views and API use `_guardian_finance_qs` / `guardian_finance_student_ids`. | OK | Keep; periodically re-audit any new parent-facing endpoints for guardian scoping. |
| **Code** | API field names and enums fixed in prior audit (issued_date, paid_at, total_amount, Invoice.Status). | Fixed | — |
| **SQL** | Remaining raw SQL is in migrations only. | OK | — |

**Verdict:** No critical issues; webhook security assumptions should stay enforced and tested.

---

### 1.4 Portal

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **Bug** | **FIXED:** `signature_pending_list` used `StudentGuardian.objects.filter(guardian=request.user)`; model field is `guardian_user`. Would raise AttributeError or return no links. | High → Fixed | Use `guardian_user` everywhere for StudentGuardian ↔ User. |
| **RBAC** | Parent views use `@parent_portal_required` / `@role_required(User.Role.PARENT)`; teacher views similarly restricted. | OK | — |
| **IDOR** | `parent_child_results(student_id)` and report views use `guardian_student_links` / `_get_guardian_student` with `can_view_results=True`. Document download uses `document.can_view(request.user)`. | OK | — |
| **Workflow** | Claim invite, link child, document library, KB, bulk letters, signature flow are consistent. | OK | — |

**Verdict:** Critical bug in signature pending list fixed; rest is in good shape.

---

### 1.5 People

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **Bug** | **FIXED:** `backend_student_create` created guardian link with `user=parent_user` and `relationship='PARENT'`, `is_primary=True`. Model has `guardian_user` (no `user`) and no `is_primary`; `Relationship` has no `PARENT` (use `GUARDIAN` or MOTHER/FATHER). Would fail at save or create wrong data. | High → Fixed | Use `guardian_user` and `StudentGuardian.Relationship.GUARDIAN` (or appropriate choice). |
| **RBAC** | `backend_student_list`, `backend_teacher_list`, `backend_student_create`, `backend_teacher_create`, `backend_classroom_create` use `@permission_required` (view/add for respective models). | OK | — |
| **Workflow** | Backend student create creates User + StudentGuardian when parent email given; teacher create creates User + TeacherProfile. | OK | — |

**Verdict:** Critical bug in backend student create fixed; permission usage is consistent.

---

### 1.6 Reports

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | Publish term and report generation use permission and approved-grades checks; guardian report views use `_get_guardian_student(request, student_id)` with `can_view_results=True`. | OK | — |
| **SQL** | BI services use Django `TruncMonth` (DB-agnostic) after prior fix. | OK | — |
| **Workflow** | Audit log for publish term; evals–reports alignment documented. | OK | — |

**Verdict:** No critical issues.

---

### 1.7 Evals

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | Compliance dashboard and extend-deadline use `@staff_member_required` and `@role_required`; grade approval uses `_user_can_review_grades`. | OK | — |
| **Workflow** | Single source for grading deadline (`SubjectAssignment.grading_deadline_at`); grade approval flow consistent. | OK | — |

**Verdict:** No gaps found.

---

### 1.8 Requests

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | Dashboard and detail use `@user_passes_test(_can_manage_requests)` (staff/superuser or role in allowed set). Requester cannot see other users’ requests; only managers see list/detail. | OK | — |
| **Workflow** | Request creation, decision application, and dashboard filters are consistent. | OK | — |

**Verdict:** No issues.

---

### 1.9 Communication

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | `group_list`, `group_create`, `group_detail`, `group_manage` use `@role_required(User.Role.TEACHER, User.Role.ADMIN, User.Role.LEADERSHIP)`; `group_join` checks department for department-scoped threads. Thread membership or staff required for detail/manage. | OK | — |
| **Workflow** | Thread creation, membership, department scope are coherent. | OK | — |

**Verdict:** No issues.

---

### 1.10 Academics (API)

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **Code** | Score distribution uses `Case`/`When`/`Count` (DB-agnostic) after prior fix. | Fixed | — |
| **RBAC** | Assessment and attendance APIs use `IsTeacherOrAdmin` or filter by child_ids from `StudentGuardian` with `can_view_results=True` for parents. | OK | — |

**Verdict:** No critical issues.

---

### 1.11 Analytics

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | Dashboard and views use `@staff_member_required`; year/term from GET validated with `get_object_or_404`. | OK | Confirm all analytics URLs are behind staff or role decorator (currently dashboard is staff-only). |
| **Workflow** | Year/term selection, deadline modes, master sheet are consistent. | OK | — |

**Verdict:** No critical issues.

---

### 1.12 Payroll

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | Dashboard and run detail use `@staff_member_required`; employee views use `_employee_for_user` for self-service. | OK | Verify all payroll list/detail URLs are staff-only (currently they are). |
| **Workflow** | Payroll run, payslip generation, leave requests are coherent. | OK | — |

**Verdict:** No critical issues.

---

### 1.13 API (apps/api)

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **RBAC** | Uses DRF permission classes (`IsAdminUser`, `IsTeacherOrAdmin`, `IsBursar`, etc.); entity API filters by `guardian_user` for parents. Profile endpoint `GET /api/auth/profile/` added in prior audit. | OK | — |
| **Security** | Parent/guardian ViewSets filter by `StudentGuardian` and `can_view_results` / finance where applicable. | OK | Audit any new parent-facing ViewSets for guardian/link filtering. |
| **Gaps** | Finance API may live under finance app URL prefix; document in API docs. | Low | Document in API_AUDIT_VS_GUIDE.md or API_COMPLETE_GUIDE.md. |

**Verdict:** Aligned with prior audit; keep documenting new endpoints.

---

### 1.14 Siteconfig

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **SQL** | `_ensure_preview_columns` uses `cursor.execute` with `cls._meta.db_table` (no user input). | OK | — |
| **Security** | Preview/maintenance middlewares use request/user as documented. | OK | — |
| **Gaps** | Report library export handlers are code-only (`REPORT_EXPORT_HANDLERS`); no admin UI to define or manage custom report logic for non-technical users. | Low | Future: consider admin UI or config-driven report handlers for advanced use cases. |
| **Workflow** | Report library, bulk letters, feature control, dashboard config are consistent. | OK | — |

**Verdict:** No critical issues; report handlers are a product gap, not a bug.

---

### 1.15 Observability

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **SQL** | Health checks use `cursor.execute("SELECT 1")` for DB liveness. | OK | — |
| **RBAC** | Ensure health/debug endpoints are not exposed to public or are behind auth in production. | Low | Confirm middleware or URL config restricts sensitive observability views. |

**Verdict:** No critical issues.

---

### 1.16 Automation

| Area | Finding | Severity | Suggestion |
|------|---------|----------|------------|
| **Gaps** | Models exist (`AutomationExecutionLog`, `AutomationApprovalQueue`) but no scheduled task runner or event-driven workflows are wired in this codebase. Module is minimal (models, admin, helpers). | Low | Future: integrate with Celery/Beat or similar to run and log scheduled tasks; use approval queue for sensitive automations. |
| **Workflow** | When used, execution log and approval queue are consistent with design. | OK | — |

**Verdict:** No security/RBAC issues; automation is underused by design so far.

---

## 2. Cross-Cutting Summary

### 2.1 Security

- **CSRF:** Only finance webhook is `@csrf_exempt`; required for callbacks and documented with IP/HMAC/rate-limit/idempotency.
- **SQL:** No user input in raw SQL; `.extra()` removed or replaced (finance API, reports BI, academics API). Remaining raw SQL is in migrations, siteconfig column check, observability health.
- **Access control:** Compliance IP/country fails open on error (documented). Guardian/parent data consistently scoped by `StudentGuardian` and `can_view_results` / `can_view_finance`.

### 2.2 Redundancies

- **Admin/staff checks:** `_is_admin_user` in accounts (and certification) vs `is_admin_or_staff` in compliance. Optional: single canonical helper in `accounts` or `core`.
- **Report handlers:** Defined only in code; no duplicate definitions found.

### 2.3 Workflow

- Evals → reports (approved grades, publish term) aligned.
- Guardian/parent flows: claim invite, link child, results, finance, signatures all use `guardian_user` and permission flags.
- Request management: only allowed roles see dashboard/detail; requester sees own flow via other UX.

### 2.4 Bugs Fixed in This Audit

1. **Portal** (`apps/portal/views_documents.py`): `signature_pending_list` used `guardian=request.user`; model field is `guardian_user`. Fixed to `guardian_user=request.user`.
2. **People** (`apps/people/views_backend.py`): `backend_student_create` used `user=parent_user` and `relationship='PARENT'`, `is_primary=True`. Model has `guardian_user` (no `user`), no `is_primary`, and no `PARENT` in Relationship. Fixed to `guardian_user=parent_user` and `StudentGuardian.Relationship.GUARDIAN`.

---

## 3. Suggestions (Prioritized)

1. **High (done):** Fix Portal signature pending list and People backend student create (guardian link).
2. **Medium:** Add tests for finance webhook security path (e.g. invalid signature, wrong provider).
3. **Low:** Centralize admin/staff check in one module and reuse in accounts + compliance.
4. **Low:** Document observability URL protection in production.
5. **Product:** Consider admin UI or config for report export handlers; consider wiring automation module to a task runner and approval flows.

---

**References:** APPS_AUDIT_REPORT.md, API_AUDIT_VS_GUIDE.md, SECURITY_AUDIT_REPORT.md, CODE_REVIEW_GAPS_REDUNDANCIES.md.
