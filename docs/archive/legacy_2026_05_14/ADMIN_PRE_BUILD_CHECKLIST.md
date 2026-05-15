# /admin build — pre-build checklist

Use this **before** starting implementation from `ADMIN_DASHBOARD_AND_SIDEBAR_PLAN.md`.

---

## 1. Admin URL names (verified)

Use these in `reverse_lazy()` for UNFOLD navigation or any admin links:

| Purpose | URL name |
|--------|----------|
| Users | `admin:accounts_user_changelist` |
| People (students) | `admin:people_studentprofile_changelist` |
| Academics (classrooms) | `admin:academics_classroom_changelist` |
| Evaluations | `admin:evals_evaluation_changelist` |
| Reports (report cards) | `admin:reports_reportcard_changelist` |
| Finance (invoices) | `admin:finance_invoice_changelist` |
| Payroll (payslips) | `admin:payroll_payslip_changelist` |
| Site Settings | `admin:siteconfig_sitesettings_changelist` |
| Compliance audit | `admin:compliance_complianceauditlog_changelist` |
| Requests (access requests) | `admin:requests_accessrequest_changelist` |
| Automation (execution log) | `admin:automation_automationexecutionlog_changelist` |

The plan doc section 2.1 used shortened names (e.g. `people_student`); the actual names are as above.

---

## 2. Sidebar source of truth (decision required)

We **override** Unfold’s sidebar: `admin/base.html` fills `block nav-sidebar` with our `admin/nav_sidebar.html` → `admin/sidebar_inner.html` → **admin/app_list.html** (data from `get_app_list()`). So **`UNFOLD["SIDEBAR"]["navigation"]` is not used** anywhere today.

- **Option A — Use Unfold’s nav:** Remove (or stop using) our nav-sidebar override and set `UNFOLD["SIDEBAR"]["navigation"]` with collapsible groups. You must add “Dashboard”, “Site settings”, and “Backend Console” as items (e.g. first group or “Quick access”) because Unfold won’t add them automatically.
- **Option B — Keep our sidebar:** Keep the override. Implement collapsible groups and domain names (Operational Core, Academic Processing, etc.) in `get_app_list()` and/or `admin/app_list.html`. Do **not** populate `UNFOLD["SIDEBAR"]["navigation"]` for the main list (it would be redundant).

**Decide before Phase 3** so you don’t implement both and create redundancy.

---

## 3. Dependencies

- **django-unfold** 0.76.0 — supports `SIDEBAR.navigation` with `collapsible` and `items` (title, link, icon).
- **django-otp**, **qrcode** — already in requirements; no extra packages for zero-cost MFA.

---

## 4. Action queue (dashboard)

- **Model:** `apps.requests.models.AccessRequest`.
- **Pending:** `status=AccessRequest.Status.PENDING`.
- Use for “Pending approvals” / “Action queue” widget (count + top N). Respect request-manager permissions when exposing in admin index.

---

## 5. MFA

- **require_mfa_roles:** Already on `SiteSettings`, in fieldset “Compliance & Payroll” (sidebar slug `compliance-payroll`).
- **require_mfa_all_staff (new):** Add `BooleanField` on `SiteSettings` (same fieldset or new “Security & MFA”); add migration; in `RequireMFAMiddleware`, if True, redirect any staff without TOTP (same bypass paths).

---

## 6. EMIS

- **Current:** `emis/admin.py` uses `@admin.register(...)` (default admin site). Default site is not mounted at `/admin/`.
- **Fix:** `from config.admin import admin_site` and `admin_site.register(EMISExport, ...)` (and other EMIS models). Add `"emis"` to `config.admin.GileadAdminSite.get_app_list()` `app_order` (e.g. section `operations` or `system`).

---

## 7. Nothing else blocking

- Site Settings already has a secondary sidebar (`settings_sidebar.html`) and `SETTINGS_NAV_GROUPS`; Security & MFA can be a new group or part of “Compliance & Payroll”.
- Unfold 0.76 supports collapsible sidebar navigation (confirmed).
- All admin URL names above resolve successfully.

You can proceed with the build using the plan and this checklist.
