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

1. **Backend** → **RBAC & Access Control** (or Django admin → AccessRole / User → feature_permissions).
2. Edit the **role** (e.g. TEACHER, PARENT) and add/remove permissions.
3. Or edit **individual user** → Feature permissions (overrides role).

After saving, sidebar and backend dashboard sections will show/hide automatically based on `action_perms` and `has_feature_permission`.

---

## 6. Quick verification

- Log in as a **teacher**: sidebar should show only Home, Account, Communication, My Workflow, Learning Management, Human Resources; no Admin Panel, People & Access, Financial Management, Analytics & Reports, Recent Activity.
- Log in as a **parent**: no Admin/People/Finance/Analytics; Recent Activity hidden; Portal Tools only if role has portal.forums / portal.video / portal.documents and feature is enabled.
- **Footer**: Admin Documentation and Activity Logs only for staff/superuser/ADMIN.
