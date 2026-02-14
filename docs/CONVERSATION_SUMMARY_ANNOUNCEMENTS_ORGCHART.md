# Conversation Summary (token saver)

## 1. Announcement module – tiered permissions
- **School-wide:** Only admins/leadership (Principal, Vice Principal, Admin, Leadership, etc.) can create. Teachers get 403 and are directed to Class or Department announcements.
- **Class announcements:** Teachers can create via `class_announcement_create` (classroom or optional department).
- **Department announcements:** Unchanged; HOD/leadership only via `department_announcement_create`.
- **Approval workflow (optional):** Site flag `announcement_allow_submit_for_approval` in `backend_feature_flags`; when True, roles in `announcement_submit_for_approval_roles` (e.g. TEACHER, COMMS_STAFF) can submit for approval. Approvers see "Pending approval" and can approve; only published announcements are visible.
- **Audit:** `AnnouncementAuditLog` logs created, updated, submitted_for_approval, approved, deactivated. `log_announcement_audit()` used in views and form save.
- **Models:** `Announcement` has `status` (draft, pending_approval, published), `approved_by`, `approved_at`. API and list/detail filter by `status=PUBLISHED`.

## 2. Fixes applied earlier in session
- **MessageThreadUpdateForm:** Pop `user` from kwargs before `super().__init__()` to fix TypeError on group manage.
- **Messages page:** `_serialize_thread()` now includes `"id": thread.id`; template uses `thread_id=t.id` and defensive `{% if t.id %}` for group_detail URL.

## 3. Org chart on teacher dashboard & profile
- **Data:** `_teacher_org_tree(user)` in `apps/accounts/views.py` builds chain (reports_to upward) + direct reports; each node has `photo_url`, `initials`, `name`, `title`, `department`, `is_self`. `get_org_chain_to_staff()` builds the chain.
- **Dashboard:** `evals/views.py` teacher dashboard now passes `teacher_org_tree`; right-hand panel shows visual org chart when `teacher_org_tree.diagram_levels` exists, else text chain. "View profile" link kept.
- **Profile:** Organization section uses same org-chart markup (ID-style cards). Profile loads `static/css/org-chart.css`.
- **Design:** ID-style cards – photo area on top (64px height), name and title below. If no profile image: **empty placeholder** (gray block, no initials in photo spot). When users upload photos, they show in that spot. All styles namespaced with `.org-chart-*` so **dashboard look is unchanged**; chart is self-contained inside its panel.
- **Files:** `templates/teacher/dashboard.html`, `templates/accounts/profile.html`, `static/css/org-chart.css`, org-chart block in `static/css/teacher-dashboard-modern.css`.

## 4. Org structure vs app
- App does **not** mirror the user’s org chart image exactly. Hierarchy is **role + `TeacherProfile.reports_to` + department**. Chart labels (Director, Deputy director, etc.) can be approximated with roles (e.g. Principal, Vice Principal) and `position_title`; the **display** is the org chart with photos/placeholders and names/titles.
