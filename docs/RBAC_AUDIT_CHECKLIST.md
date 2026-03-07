# RBAC Permission Audit Checklist

Use this checklist to tighten what each role can see and do. Permissions are managed under **Backend → RBAC & Access Control** (and via Django Admin → Users / Access Roles).

**When to run:** Do one full audit after initial setup, then again whenever you change roles or add new users. Keeps teachers and parents from seeing admin-only links and data.

---

## 1. Teachers

**Goal:** Teachers see only Learning Management (marks, attendance) and their own HR (payslips, leave). No Admin Panel, People & Access, Analytics & Reports, Financial Management, or Recent Activity.

| Check | Action |
|-------|--------|
| Sidebar | Teachers no longer see Admin Panel, People & Access, Financial Management, Analytics & Reports, or Recent Activity (code already enforces this). |
| Role permissions | Ensure **TEACHER** role does **not** have: `settings.manage`, `reports.manage`, `finance.view`, `finance.manage`, `data.access`, `communication.manage` (unless you want a specific teacher to have them). |
| Portal tools | Teachers get `portal.forums`, `portal.video`, `portal.documents` by default (migration 0011). Remove from TEACHER role if they should not see Community / Video / Documents. |
| Payroll | `employee_payslips` and `employee_leave` are already scoped to the current user’s payroll profile. |

---

## 2. Parents

**Goal:** Parents see only their children’s data, finance (if granted), and allowed portal tools. No admin or other users’ info.

| Check | Action |
|-------|--------|
| Academic Stats | Only the parent’s linked children appear in rankings and improvement (code already enforces this). |
| Finance & Fees | Data is scoped to guardian links and finance opt-in; 500 fixed. |
| Role permissions | Ensure **PARENT** role has only what you need: e.g. `finance.view` if they can see fees; remove `reports.manage`, `data.access`, `settings.manage` unless required. |
| Portal tools | Parents get `portal.forums`, `portal.video`, `portal.documents` by default. Remove from PARENT role if they should not see them. |

---

## 3. Admin-like roles (ADMIN, LEADERSHIP, IT_ADMIN, BURSAR)

**Goal:** Each role sees only what they need; avoid granting “everything” by default.

| Permission | Typical use | Consider removing from |
|------------|-------------|-------------------------|
| `settings.manage` | Site settings, theme, backend config | BURSAR, IT_ADMIN (unless intended) |
| `reports.manage` | Publish results, report library | BURSAR |
| `finance.view` / `finance.manage` | Finance dashboard, invoices | ADMIN/LEADERSHIP if they should not see finance |
| `data.access` | Backend data / exports | Narrow to specific roles |
| `communication.manage` | Announcements, groups | Narrow to comms roles |
| `portal.manage` | Portal feature toggles | Usually admin only |

---

## 4. Portal tools (per-feature RBAC)

| Permission | Controls | Default roles (migration 0011) |
|------------|----------|---------------------------------|
| `portal.forums` | Community / Forums link and page | PARENT, TEACHER, ADMIN, LEADERSHIP, IT_ADMIN |
| `portal.video` | Video Hub link and page | Same |
| `portal.documents` | Documents link and page | Same |

**To restrict:** In RBAC & Access Control, remove the corresponding `portal.*` permission from the role. The sidebar and `portal_feature_page` view both enforce these permissions.

---

## 5. Footer and sidebar

| Area | RBAC |
|------|------|
| Footer “Support & Help” | Admin Documentation and Activity Logs only for staff/superuser/ADMIN. |
| Footer “Quick Links” | Backend Dashboard only when `can_settings` or `can_data_access`; teacher/parent links by role and permission. |
| Sidebar “Recent Activity” | Hidden for TEACHER and PARENT. |
| Sidebar “Portal Tools” | Each link shown only when feature is enabled and user has the matching `portal.*` permission. |

---

## 6. Quick audit steps

1. **List roles:** Backend → RBAC & Access Control → review each Access Role.
2. **For each role:** Remove permissions that role should not have (e.g. remove `settings.manage` from TEACHER if still present).
3. **Test as that role:** Log in as a user with that role and confirm sidebar, backend dashboard, and footer match expectations.
4. **Portal tools:** If parents/teachers should not see Community or Video, remove `portal.forums` / `portal.video` from their role(s).

---

## 7. Files that enforce RBAC (reference)

| Area | File(s) |
|------|--------|
| Sidebar (config-driven) | `apps/siteconfig/portal_sidebar_items.py` |
| Sidebar (static fallback) | `templates/partials/portal_sidebar.html` |
| Footer | `templates/components/dashboard_footer.html` |
| Portal tools view | `apps/portal/views.py` → `portal_feature_page` (checks `portal.*` permission) |
| Backend dashboard | `templates/accounts/backend_dashboard.html` (action_perms), `apps/accounts/views.py` (action_perms) |
| Permissions model | `apps/accounts/models.py` → User.has_feature_permission, Permission |

After changing role permissions, users may need to log out and back in (or clear session) for permission checks to reflect the new assignments.
