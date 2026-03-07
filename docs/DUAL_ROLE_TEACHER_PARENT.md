# Dual-Role: Teacher + Parent (Same Account)

**Purpose:** How the system supports one user who is both a teacher and a parent ("two hats") with a single account and no duplicate data.

---

## 1. Single identity

- Every person has **one** User record. A teacher who is also a parent does **not** get a second account.
- **Primary role** (`User.role`) stays as the main role (e.g. TEACHER). The user can also have **guardian links** (StudentGuardian) to their children.
- **Teacher hat:** User has a `TeacherProfile`.  
- **Parent hat:** User has at least one `StudentGuardian` link (guardian of a student).

---

## 2. Data and validation

- **StudentGuardian** allows `guardian_user.role` to be **PARENT** or **TEACHER**. So a user with role TEACHER can be linked as a guardian without changing their primary role.
- **TeacherProfile** still requires a teacher-aligned role (TEACHER, DEPT_LEAD, LEADERSHIP). A user with role PARENT cannot have a TeacherProfile unless their role is changed to TEACHER (or they have both: primary role TEACHER + guardian links).

---

## 3. Portal: role switcher and effective role

- When a user has **both** hats (TeacherProfile + at least one StudentGuardian), the portal shows a **role switcher** in the sidebar: "Switch view: Teacher | Parent."
- Choosing a view sets **session** `active_portal_role` to `TEACHER` or `PARENT`. The **sidebar** and **post-login redirect** use this **effective portal role** so the user sees either teacher sections or parent sections, not both mixed.
- If the user has only one hat, no switcher is shown; behavior is unchanged (single role).

---

## 4. Access control

- **Parent-only views** (e.g. parent dashboard, parent finance): allowed if the user has the **parent hat** (at least one StudentGuardian link), regardless of primary role. So a teacher with guardian links can open these when they switch to Parent view.
- **Teacher-only views** (e.g. marks entry, teacher workflow): allowed if the user has the **teacher hat** (TeacherProfile).
- **Object-level:** e.g. viewing a student's data or an invoice is allowed if the user has a **guardian link** to that student (with the right flags like `can_view_results` / `can_view_finance`), not only when `user.role == PARENT`.

---

## 5. How to set up a dual-role user

1. Create or use a **User** with primary role **TEACHER** (or PARENT if they are mainly a parent who also teaches).
2. Ensure they have a **TeacherProfile** (for teacher hat).
3. Add **StudentGuardian** records linking that user to their children (same user as `guardian_user`). No second account; the validation allows TEACHER as guardian.
4. On login, they see the portal for their primary role; if they have both hats, the sidebar shows "Switch view: Teacher | Parent" and they can switch and get the appropriate dashboard and nav.

---

## 6. Improvements and optional behaviour

- **Last-used role persisted:** When the user switches portal role, `UserPreference.last_portal_role` is updated. On the next login (or when session is empty), the effective role is restored from this preference so they land in the same view (Teacher or Parent).
- **Site-level default for dual-role:** In Site Settings (Feature Toggles), **Default portal role (dual-role)** can be set to Teacher or Parent. When a dual-role user has no saved preference yet, they are assigned this default and it is written to their `UserPreference.last_portal_role`. Leave blank to use the user's primary role (`user.role`).
- **Header label:** When the role switcher is shown, the portal header displays "Viewing as: Teacher" or "Viewing as: Parent" in the topbar context strip.
- **Cache:** Hat checks (`has_teacher_hat` / `has_parent_hat`) are cached on the request in the site context processor (`request._portal_teacher_hat`, `request._portal_parent_hat`) so sidebar and effective-role logic do not repeat DB queries.
- **Admin:** On the User change form, a read-only "Portal roles (dual-role)" section shows "Also guardian of: [list of students]" when the user has guardian links.
- **Accessibility:** The role switcher has `role="group"`, `aria-labelledby`, and `aria-label` on each link ("Switch to Teacher view" / "Switch to Parent view") for screen readers. All labels use `{% trans %}` for i18n.
- **Tests:** `apps/accounts/tests/test_dual_role_teacher_parent.py` covers dual-hat access to parent and teacher views, session switch, redirect by session role, and guardian_student_links scoping.

## 7. Code references

| What | Where |
|------|--------|
| Hat helpers | `apps/accounts/portal_roles.py` (`has_teacher_hat`, `has_parent_hat`, `get_effective_portal_role`) |
| Last portal role | `apps/siteconfig.models.UserPreference.last_portal_role`; set in `switch_portal_role`, read in `get_effective_portal_role` |
| Site default for dual-role | `apps/siteconfig.models.SiteSettings.default_portal_role_dual_role`; used in `get_effective_portal_role` when user has no saved preference |
| StudentGuardian validation | `apps/people/models.py` (`StudentGuardian.clean`) |
| Access (decorator + object) | `apps/accounts/decorators.py` (`role_required`, `parent_can_access_student`, `parent_can_access_invoice`) |
| Sidebar / redirect | `apps/siteconfig/portal_sidebar_items.py`, `apps/accounts/views.py` (`redirect_view`, `switch_portal_role`) |
| Role switcher UI | `templates/partials/portal_sidebar.html` |
| Header "Viewing as" | `templates/portal_base.html` (topbar-context-strip) |
| Context (switcher, effective role, cache) | `apps/siteconfig/context_processors.py` |
| Admin "Also guardian of" | `apps/accounts/admin.py` (`UserAdmin.guardian_of_display`) |
| Integration tests | `apps/accounts/tests/test_dual_role_teacher_parent.py` |

---

## 8. Summary

- One user, one account; teacher and parent are **roles/hats** derived from TeacherProfile and StudentGuardian.
- Dual-hat users get a **role switcher** and session-based **effective portal role** so the UI shows either Teacher or Parent view.
- Data is scoped correctly: parent views use guardian links only; teacher views use teacher scope only.
