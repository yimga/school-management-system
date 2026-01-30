# Smoke Test Steps

Quick manual checks after changes to admin, backend, portal, sidebar, or themes.

## Prerequisites

- Run migrations: `python manage.py migrate`
- Create a superuser and (optional) teacher/parent users for testing
- Start server: `python manage.py runserver`

## 1. Django check

```bash
python manage.py check
```

Expect: "System check identified no issues."

## 2. Admin (`/admin/`)

1. Log in as staff/superuser.
2. Open `/admin/`.
3. Confirm: sidebar visible, model groups, theme toggle (Light/Dark/System) in nav.
4. Confirm: admin index shows config-driven content (accent, tagline, portal stats if configured).
5. Open a changelist (e.g. People → Students). Confirm same sidebar and theme.

## 3. Backend console

1. Log in as staff (e.g. ADMIN role or is_staff).
2. Open backend dashboard (e.g. `/accounts/` or link from portal).
3. Confirm: sidebar has "Django Admin" in System Configuration / staff section.
4. Confirm: theme (light/dark) from Site Settings → backend_console_theme if set.

## 4. Teacher dashboard & sidebar

1. Log in as a user with role **TEACHER**.
2. Go to teacher dashboard (e.g. `/portal/` or teacher home).
3. **Sidebar:** Confirm teacher sees only:
   - Home: Dashboard, My Profile, Preferences, Notifications, Knowledge Base
   - Communication: Messages, Message Groups
   - My Workflow, Learning Management (Enter Marks, Marks History, Attendance)
   - Human Resources (Payslips, Leave, Pay History)
4. **Do not see:** Recent Activity block, Admin Panel, Backend Console, System Configuration, Django Admin, People & Access, Academic Management, Financial Management, Analytics & Reports.

## 5. Parent dashboard & sidebar

1. Log in as a user with role **PARENT**.
2. Go to parent dashboard (e.g. `/portal/` or parent home).
3. **Sidebar:** Confirm parent sees only:
   - Home: Dashboard, My Profile, Preferences, Notifications, Knowledge Base
   - Communication: Contact School
   - My Workflow, Children & Learning (My Children, Finance & Fees, Link Child, Claim Invite), Performance Tracking (Academic Stats)
4. **Do not see:** Recent Activity block, Admin Panel, Backend Console, System Configuration, Django Admin, teacher-only or staff-only sections.

## 6. RBAC summary

| Item                 | Teacher | Parent | Staff/Admin |
|----------------------|---------|--------|-------------|
| Recent Activity      | No      | No     | Yes         |
| Django Admin link    | No      | No     | Yes         |
| System Configuration| No      | No     | Yes         |
| Backend Console      | No      | No     | Yes         |
| Portal Tools (if on) | Yes     | Yes    | Yes         |
| About Portal         | Yes     | Yes    | Yes         |

## 7. Accessibility (manual)

- **Skip link:** Tab from top of portal page; first focusable should be "Skip to main content"; Enter goes to main content.
- **Theme toggle:** Focus theme button; visible focus ring (e.g. outline).
- **Sidebar (admin):** Recent Activity header: focus with Tab, toggle with Enter or Space.

## 8. Optional: automated accessibility

If `ALLOWED_HOSTS` includes `'testserver'` (e.g. in test settings):

```bash
python manage.py check_accessibility --pages portal
python manage.py check_accessibility --pages admin
```

On Windows, if the command fails on Unicode (e.g. checkmarks), run with `PYTHONIOENCODING=utf-8` or use the test suite:

```bash
python manage.py test apps.siteconfig.tests.test_accessibility
```
