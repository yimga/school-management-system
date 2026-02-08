# RBAC Permission Audit Checklist

Use this checklist to tighten visibility by role. The sidebar and backend dashboard already gate by **feature permissions**; if a role still sees too much, **remove the corresponding permission** from that role in **RBAC & Access Control** (or Django admin).

---

## 1. Permissions that control visibility

| Permission | What it controls |
|------------|------------------|
| **settings.manage** | Backend Console, Workflow Center, Site Settings, Customizer, RBAC & Access Control |
| **reports.manage** | Publish Results, Report Library, Report Card Builder, Reports section, Teacher Marks/Reports links |
| **data.access** | Data exports, Backend Dashboard “Reports” / data sections |
| **finance.view** | Finance & Fees (parent), Finance Dashboard link, finance widgets |
| **finance.manage** | Finance management, invoicing, Finance Dashboard |
| **attendance.manage** | Attendance dashboards, attendance management |
| **portal.manage** | Portal features (admin control); not the same as portal tools access |
| **portal.forums** | Portal Tools → Community / Forums (when feature enabled) |
| **portal.video** | Portal Tools → Video Hub (when feature enabled) |
| **portal.documents** | Portal Tools → Documents (when feature enabled) |
| **communication.manage** | Announcements, communication center |
| **student.manage** | Student control, referrals |

---

## 2. Role audit: what to remove for TEACHER

To keep teachers to **Learning Management + HR only** (no admin/people/finance/analytics), ensure the **TEACHER** role does **not** have:

- [ ] **settings.manage** – no Backend/Workflow/Site Settings
- [ ] **reports.manage** – remove if teachers must not see Publish Results / Report Library / Report Card Builder (they may keep it for marks/reports only; then leave it)
- [ ] **data.access** – no data exports / backend data sections
- [ ] **finance.view** / **finance.manage** – no Finance Dashboard
- [ ] **communication.manage** – remove if teachers must not create Announcements (they often keep Messages only)

Teachers **should** keep (if you want them to have):

- [ ] **attendance.manage** – for their attendance views
- [ ] **reports.manage** – if they use marks entry and report-related views
- [ ] **portal.forums**, **portal.video**, **portal.documents** – only if they should see Portal Tools (Community, Video, Documents)

---

## 3. Role audit: what to remove for PARENT

Parents should only see **their children’s data**, Finance & Fees (when granted), and allowed portal tools. Ensure **PARENT** role does **not** have:

- [ ] **settings.manage**
- [ ] **data.access**
- [ ] **reports.manage** – remove if parents must not see “Reports” / report builder (they usually only see report cards for their children)
- [ ] **communication.manage** – remove if parents must not create Announcements
- [ ] **portal.manage** – admin control of portal; parents should not have this

Parents **should** keep (if you want them to have):

- [ ] **finance.view** – to see Finance & Fees for linked children (when guardian link has finance access)
- [ ] **portal.forums**, **portal.video**, **portal.documents** – only if they should see Portal Tools

---

## 4. Portal Tools (Community, Video, Documents)

- **portal.forums**, **portal.video**, **portal.documents** are **per-feature** permissions.
- Default migration assigns all three to: PARENT, TEACHER, ADMIN, LEADERSHIP, IT_ADMIN (so behaviour is unchanged until you remove them).
- To restrict: remove **portal.forums** or **portal.video** or **portal.documents** from a role in RBAC & Access Control; that role will no longer see that link (and will get 403 if they open the URL directly).

---

## 5. Where to change permissions

1. **Backend** → **RBAC & Access Control** (requires **settings.manage**; or Configuration Engine → Accounts → AccessRole / User → feature_permissions).
2. **Edit a role’s permissions:** In RBAC & Access Control, open **Existing Roles** → **Edit** next to the role; or in Configuration Engine go to Accounts → Access roles and edit the role there.
3. **Assign roles to a user:** In RBAC & Access Control use **Assign Roles to User** (select user, check one or more roles, Save). This sets the user’s **AccessRoles** (multiple roles allowed). The user’s **primary role** (User.role, e.g. for display) can be set in Configuration Engine when editing the user; changing User.role there also auto-applies the corresponding AccessRole permissions.
4. **Individual user overrides:** Edit the user in Configuration Engine and set **Feature permissions** (overrides role).

**Auto-apply:** When you create or change a user’s **role** (User.role) in Configuration Engine, the system automatically assigns the matching AccessRole(s) so permissions apply without a separate step. Use **Assign Roles to User** to add extra roles or override.

**Temporary role grants:** Use **Grant role with expiry** on the RBAC page (or Configuration Engine → Accounts → Temporary role grants) to give a user a role until a set date (e.g. an auditor for one month). Permissions from that role apply only while the grant is active (expires_at in the future, and optional valid_from in the past). Active temporary grants are listed on the RBAC page; run `python manage.py list_expired_temporary_grants` to list expired grants.

After saving, sidebar and backend dashboard sections show/hide based on `action_perms` and `has_feature_permission`.

---

## 6. Quick verification

- Log in as a **teacher**: sidebar should show only Home, Account, Communication, My Workflow, Learning Management, Human Resources; no Admin Panel, People & Access, Financial Management, Analytics & Reports, Recent Activity.
- Log in as a **parent**: no Admin/People/Finance/Analytics; Recent Activity hidden; Portal Tools only if role has portal.forums / portal.video / portal.documents and feature is enabled.
- **Footer**: Admin Documentation and Activity Logs only for staff/superuser/ADMIN.
