# RBAC: Dashboard visibility

Users should only see features they are allowed to use. The backend dashboard and other dashboards gate content by role and permissions.

## Backend dashboard (`/authentication/backend/`)

Access to the page requires `settings.manage` and `_is_admin_user` (staff, superuser, or role ADMIN). Within the page, **action_perms** control which sections and buttons are shown:

| Permission key   | Who has it | What is shown |
|------------------|------------|----------------|
| **people**       | ADMIN, LEADERSHIP, IT_ADMIN, SUPERADMIN (or superuser) | Quick Actions: Add Student, Add Teacher, Onboard wizards; Report Card Builder link; Analytics filters; Attendance snapshot; Grade imports; Entity Management; Frontend orchestration; Recommended next steps (classrooms, students, teachers, Workflow Center, Publish results) |
| **finance**      | ADMIN, LEADERSHIP, IT_ADMIN, BURSAR, SUPERADMIN (or superuser) | Quick Actions: Create Invoice, Finance Console; Finance & trend card; Pending referrals card; Finance access banner; Pending finance access request alert |
| **site_settings**| Can manage settings (admin-like + `settings.manage`) | Quick Actions: Site Settings; Portal insights card; RBAC snapshot + Permissions overview |
| **admin_panel**  | staff, superuser, ADMIN, IT_ADMIN | Sidebar/Quick Actions: Admin Panel link; RBAC snapshot + Permissions overview (with site_settings) |

- **Welcome header:** Report Card Builder link is shown only if `action_perms.people`.
- **Recommended next steps:** Built in the view; only steps the user is allowed to perform (people-gated steps) are included.
- **Finance alerts:** Pending finance access request alert and finance access banner are shown only if `action_perms.finance`.
- **Rows:** Finance/Attendance row is shown only if `action_perms.finance or action_perms.people`. Portal insights / Pending referrals / Grade imports row only if at least one of `site_settings`, `finance`, `people`.

## Where it’s defined

- **View:** `apps/accounts/views.py` – `backend_dashboard()` builds `action_perms` and filters `recommended_next_steps` by `action_perms`.
- **Template:** `templates/accounts/backend_dashboard.html` – sections and buttons are wrapped in `{% if action_perms.people %}`, `{% if action_perms.finance %}`, etc.
- **Sidebar items:** Same view builds `available_sidebar_items` with `allow=...` per item; only allowed items are included.

## Other dashboards

- **Parent dashboard:** Uses `can_view_results`, `can_view_finance`, etc., from context (guardian/role).
- **Footer:** `templates/components/dashboard_footer.html` uses `has_feature_permission` and `has_role` for links.

When adding a new backend widget or action, gate it with the appropriate `action_perms` key (and add the key to the view if it’s a new permission area).

---

## Sidebar (portal left nav)

The **portal sidebar** (`templates/partials/portal_sidebar.html`) is RBAC‑aware so users only see links they have permission for. Permissions come from the user’s role(s) and/or explicit feature permissions (admin‑granted).

### Admin Panel block (staff / ADMIN / LEADERSHIP / IT_ADMIN / BURSAR / SUPERADMIN)

- **Backend** (Backend Console, Workflow Center): only if `settings.manage` or superuser.
- **People & Access** (Student Profiles, Guardians, Auth Groups, RBAC): only if `reports.manage` or `data.access` or `settings.manage` or superuser.  
  - **RBAC & Access Control** link: only if `settings.manage` or superuser.
- **Academic Management** (Evaluation Admin, Class/School Ranking, Publish Results): only if `reports.manage` or superuser.
- **Financial Management** (Finance Dashboard, Payroll): only if `finance.view` or `finance.manage` or superuser.
- **Analytics & Reports** (Analytics, Report Library, Report Card Builder): only if `reports.manage` or `data.access` or superuser.
- **Communication** (Message Groups, Announcements): only if `communication.manage` or superuser. (Messages link is shown to all in this block.)

### Parent block

- **Finance & Fees**: only if `finance.view` or `finance.manage` (e.g. granted via guardian link or role).

### System Configuration (bottom)

- **Site Settings**, **Region Configuration**: only if `settings.manage` or superuser.

### Implementation

- Sidebar uses `{% load accounts_extras %}` and the filters `has_feature_permission` and `has_role`.
- Each section/link is wrapped in `{% if request.user|has_feature_permission:"..." or request.user.is_superuser %}` (or the appropriate permission). Superuser always sees everything; others only see what their permissions allow.
