# RBAC & Portal: Ideas and Summary

Summary of changes made and ideas for the points you raised.

---

## 1. Parent dashboard – Academic Stats (done)

**Requirement:** Academic Stats must focus on the parent’s children only; no personal information of other kids.

**Done:**

- **`portal_stats` (Academic Stats)** now:
  - Builds **top_students** only from the parent’s linked children (no other students in the class).
  - Filters **improvement_rows** to only the parent’s children.
- **`portal_stats`** already used `guardian_students(request.user, results_only=True)` for `students`; specialty and widget data were already scoped. The fix ensures **rankings** and **improvement** lists show only the parent’s children.

---

## 2. Finance & Fees page – 500 error (done)

**Requirement:** Fix 500 on parent Finance & Fees page.

**Done:**

- **Cause:** In `parent_finance`, `finance_summary` and `finance_access_banner` used `finance_paid_pct`, `finance_total`, `finance_paid`, and `can_view_finance` before they were defined (they were computed later from `invoices_qs`).
- **Fix:** Moved the block that computes `students`, `invoices_qs`, `aggregates`, `total_due`, `balance`, `paid`, and then `finance_paid_pct` and `can_view_finance` **above** the construction of `finance_summary` and `finance_access_banner`, so those variables exist when building the banner.

---

## 3. Portal preferences – full access for all users (already the case)

**Requirement:** All users should have full access to set their own portal/dashboard preferences.

**Current behaviour:**

- **`siteconfig:user_preferences`** is protected only with **`@login_required`** (no staff or role check).
- Each user gets their own **UserPreference** and **DashboardUserPreference** via `get_or_create(user=request.user)`.
- Parents, teachers, and admins can all open **Preferences** from the sidebar and change theme, dashboard view, notifications, etc., for their own account.

So preferences are already user-centric and available to all authenticated users. If something is still restricted (e.g. a specific field or page), say which one and we can adjust.

---

## 4. Teacher sidebar – Admin / People / Analytics / Finance / Recent Activity (done)

**Requirement:** On teacher profile sidebar, remove: Admin Panel, People & Access, Analytics & Reports, Financial Management, Recent Activity. Keep only what they need (Academic Management, HR – user-centric).

**Done:**

- **Config-driven sidebar** (`apps/siteconfig/portal_sidebar_items.py`):  
  Admin Panel, People & Access, Financial Management, Analytics & Reports are added only when `(is_staff or is_superuser or role in ("ADMIN", "LEADERSHIP", "IT_ADMIN"))` **and** `role != "TEACHER"`. So teachers no longer get those sections even if they are staff.
- **Static fallback** (`templates/partials/portal_sidebar.html`):  
  The same admin block is shown only when `request.user.role != 'TEACHER'` **and** `(is_staff or is_superuser or role == 'ADMIN')`. Teachers never see Admin Panel, People & Access, Academic Management (admin), Financial Management, Analytics & Reports in the sidebar.
- **Recent Activity** in the sidebar is shown only when `request.user.role != 'TEACHER'` and `request.user.role != 'PARENT'`, so teachers and parents no longer see other users’ activity.

Teachers still see:

- **Learning Management:** Enter Marks, Marks History, Attendance.
- **Human Resources:** Payslips, Leave Requests, Pay History (their own).

---

## 5. Teacher HR & Academic – user-centric (already so)

**Requirement:** HR should show their pay, payslip, leave; analytics should focus on their classes and profile.

**Current behaviour:**

- **Payslips / Pay History:** `payroll:employee_payslips` and `payroll:employee_leave` are intended to be employee-scoped (the logged-in teacher). Any backend that still shows all staff should be restricted to the current user’s records.
- **Learning Management:** Marks entry and attendance are typically scoped to the teacher’s classes/subjects.

If you still see school-wide finance or analytics in the teacher portal, we can add explicit filters (e.g. by `request.user` or teacher_profile) in those views.

---

## 6. Portal tools – should parents and teachers have access?

**Current behaviour:**

- **Portal Tools** (Community / Forums, Video Hub, Documents) are shown in the sidebar when `SITE.portal_features` has `forums`, `video`, or `documents` enabled. They are **not** gated by role in the template, so any authenticated user (including parents and teachers) can see and open them if the feature is on.

**Ideas:**

- **Option A – Keep as is:** Parents and teachers see Portal Tools when enabled; good for community and document sharing.
- **Option B – Role-based visibility:** Show “Portal Tools” only to certain roles (e.g. staff + parents, or only parents, or only teachers) via a new site setting (e.g. `portal_tools_roles: ["PARENT", "TEACHER"]`) and template checks.
- **Option C – Per-feature RBAC:** Add permissions like `portal.forums`, `portal.video`, `portal.documents` and show each link only if the user has the corresponding permission (and the feature is enabled). This aligns with “everything RBAC compliant” and allows fine-grained control.

Recommendation: **Option C** if you want full RBAC; **Option A** if you want minimal change and are fine with “all logged-in users when feature is on”.

---

## 7. RBAC – “I still see a lot of stuff”

**Done in this pass:**

- Teacher sidebar: Admin Panel, People & Access, Financial Management, Analytics & Reports, and Recent Activity removed for teachers.
- Parent Academic Stats: only parent’s children (no other kids’ info).
- Parent Finance & Fees: 500 fixed; data remains scoped to guardian links and finance opt-in.

**Further tightening you can do:**

- **Backend dashboard:** Already gated by `action_perms` (people, finance, site_settings, admin_panel) in the template and in the view. If a role still sees too much, reduce the permissions assigned to that role in RBAC & Access Control.
- **Sidebar:** If you use **config-driven** sidebar (`portal_sidebar_order` set in Site Settings), the same role logic in `portal_sidebar_items.py` applies. If you use **static** sidebar, the template now excludes teachers from the admin block and excludes teachers/parents from Recent Activity.
- **Granular permissions:** Use feature permissions (e.g. `finance.view`, `reports.manage`) on roles so that “Finance & Fees” or “Publish Results” appear only for users who have the right permission, instead of showing by role alone.

---

## 8. Footer – “did not change as I would have expected”

**Current footer:**

- **Dashboard footer** (`components/dashboard_footer.html`) is included from `portal_base.html` and shows: branding, support hours, WhatsApp/email, accordion sections (Support & Help, Quick Links, Contact & Status, Legal & Info), status row, and meta/copyright. It was previously made more compact (reduced height, accordion on mobile).

**If it “did not change” after deployment:**

- Ensure you deployed the branch that contains the footer template and CSS (e.g. `main` or `improvements`) and used **Clear build cache & deploy** on Render so the new markup and styles are served. See **docs/DEPLOYMENT_BACKEND_DASHBOARD.md** (section 6).

**If you want different content or behaviour:**

- **Shorter / smaller:** Reduce text, remove a section, or hide the accordion on desktop and keep a single line (e.g. “Support | Contact | Legal”).
- **Different links:** Change Quick Links / Legal to point to specific pages (e.g. parent dashboard, teacher portal, contact form) and hide admin-only links for non-staff (footer already has some RBAC in links).
- **Theme:** Ensure footer CSS uses the same theme variables as the rest of the portal (e.g. `data-theme="dark"`) so it matches the rest of the page.

If you describe what you expected (e.g. “one line”, “no accordion”, “only contact and legal”), we can align the footer markup and styles with that.

---

## RBAC permission audit

To tighten what each role sees, use **[docs/RBAC_PERMISSION_AUDIT_CHECKLIST.md](RBAC_PERMISSION_AUDIT_CHECKLIST.md)**. It lists which permissions control which links/sections and what to remove for TEACHER and PARENT.

---

## Quick reference – files touched in this pass

| Area | File(s) |
|------|--------|
| Parent Finance 500 | `apps/portal/views.py` – `parent_finance` (variable order) |
| Academic Stats – parent’s children only | `apps/portal/views.py` – `portal_stats` (filter `top_students`, `improvement_rows`) |
| Teacher sidebar – no Admin/People/Finance/Analytics/Recent Activity | `apps/siteconfig/portal_sidebar_items.py` (exclude `role == "TEACHER"` from admin block); `templates/partials/portal_sidebar.html` (same + hide Recent Activity for TEACHER and PARENT) |

Preferences, teacher HR, portal tools, and footer are either already correct or covered above as ideas/options.
