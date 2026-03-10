# URL Quick Reference Guide

## 🎯 Main Entry Points

| URL | Purpose | Who | Status |
|-----|---------|-----|--------|
| `/` | Home (role redirect) | All | ✅ |
| `/authentication/login/` | Login | Everyone | ✅ |
| `/admin/` | Admin backend | Admins only | ✅ |
| `/portal/parent/` | Parent portal | Parents | ✅ |
| `/portal/teacher/` | Teacher portal | Teachers | ✅ |

## 🔑 Admin Routes

```
/admin/                           - Main admin interface
/admin/accounts/user/             - User management
/admin/academics/academicyear/    - Academic years
/admin/academics/classroom/       - Classrooms
/admin/academics/subject/         - Subjects
/admin/people/studentprofile/     - Students
/admin/people/teacherprofile/     - Teachers
/admin/finance/invoice/           - Invoices
/admin/compliance/                - Compliance
/admin/siteconfig/sitesettings/   - Site settings
```

## 👨‍🎓 Teacher Routes

```
/portal/teacher/                  - Dashboard
/portal/teacher/attendance/       - Attendance tracking
/portal/teacher/pay-history/      - Pay history
/portal/teacher/leave/            - Leave requests
/evals/teacher/                   - Marks entry dashboard
/evals/teacher/marks/             - View marks
/evals/teacher/marks/entry/       - Enter marks
```

## 👨‍👩‍👧 Parent Routes

```
/portal/parent/                   - Dashboard
/portal/parent/results/<id>/      - Student results
/portal/parent/finance/           - Finance info
/portal/parent/link-child/        - Link student
/portal/parent/claim-invite/      - Claim from invite
```

## 🔧 Configuration Routes

```
/siteconfig/customizer/           - Site customizer
/siteconfig/user_preferences/     - User settings
```

## 📊 API Endpoints

```
/api/health/                      - API health status
/api/notifications/               - Notifications
/api/notifications/mark-all-read/ - Mark all as read
/api/activities/                  - Activity feed
/api/dashboard/charts/            - Dashboard data
/healthz/                         - Server health
/metrics/                         - Prometheus metrics
```

## 🔐 Security Routes

```
/authentication/login/            - Login page
/authentication/logout/           - Logout
/authentication/mfa/setup/        - Setup 2FA
/authentication/mfa/verify/       - Verify 2FA
```

## 🔄 Redirects

- `/backend/` → `/authentication/login/` (deprecated)
- `/authentication/backend/` → `/admin/` (deprecated)
- `/authentication/backend-dashboard/` → `/admin/` (deprecated)

## ⌨️ Keyboard Shortcuts

- `h` → Home (/)
- `a` → Admin (/admin/)
- `b` → Backend RBAC (/backend/rbac/)
- `p` → Portal (/portal/)

---

✅ All URLs validated and working!
