# Dashboards and Links - Connectivity Reference

Entry points, post-login redirects, and key URL names so dashboards and links stay connected.

## Entry Points

- `/` - Home: unauthenticated to `/authentication/login/`; authenticated to `/authentication/redirect/` (role-based).
- `/authentication/login/` - Login. POST to `/authentication/redirect/` or safe `next` param.
- `/portal` - Redirects to `portal:parent_dashboard` (`/portal/parent/`).

## Post-Login Redirect

- Staff with settings.manage: `accounts:workflow_center` or `accounts:backend_dashboard`.
- TEACHER: `portal:teacher_workflow` or `evals:teacher_dashboard`.
- PARENT: workflow/finance/performance or `portal:parent_dashboard`.
- Other: `admin:index` (`/admin/`).

## Dashboards by Role

- Admin/Staff Backend: `/authentication/backend/` (or `/backend` redirect).
- Django admin: `/admin/`.
- Teacher evals: `/evals/teacher/`.
- Teacher portal: `/portal/teacher/`.
- Parent: `/portal/parent/`.

## Key URL Names

accounts:login, accounts:redirect, accounts:backend_dashboard, accounts:workflow_center, accounts:user_profile, accounts:rbac. portal:parent_dashboard, portal:parent_finance, portal:link_child, portal:claim_invite. portal:teacher_workflow, portal:teacher_attendance, portal:teacher_pay_history, portal:teacher_leave. evals:teacher_dashboard, evals:teacher_marks_entry, evals:teacher_marks_list. admin:index. siteconfig:user_preferences, siteconfig:customizer, siteconfig:feature_control_audit. finance:dashboard, payroll:dashboard, payroll:employee_payslips, payroll:employee_leave.

## Login Form

POST to current URL. On success redirect to accounts:redirect or safe next. Page links: accounts:claim_invite, portal:parent_dashboard, portal:link_child, siteconfig:user_preferences, siteconfig:customizer.
