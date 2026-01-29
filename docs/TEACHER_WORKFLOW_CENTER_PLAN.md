# Teacher Workflow Center – Implementation Plan

**Date:** January 28, 2026  
**Goal:** A teacher-facing “Workflow Center” comparable to the admin Workflow Center: clear steps, progress (what you’ve done → where you are → what’s next), RBAC-compatible, using existing features where possible. Aligned with Cameroon teacher flow (Anglophone & Francophone, MINEDUB/MINESEC).

**Scale:** Platform must remain flexible and support **20,000+ users** (teachers + students). All design choices must be compatible with pagination, indexing, and efficient queries.

---

## 1. Teacher flow (your guidance) vs current system

| Phase | Your flow | What exists today | Gap |
|-------|-----------|-------------------|-----|
| **1. Onboarding & profile** | Registration, credentials/CV upload; assignment to subjects & classes; schedule setup (timetable). | Teacher onboarding wizard (`portal:teacher_onboarding`), admin create teacher + SubjectAssignment (class/subject), TeacherProfile (department, position). Scheduling models exist (Room, TimeSlot, Schedule, ScheduleEntry) but **no teacher-facing timetable UI**. | Timetable view for teacher (read-only); optional document upload for credentials/CV (can use Document Library or profile attachments). |
| **2. Daily operations** | Check-in/check-out; lesson plan submission for principal approval; teachers log student attendance. | **TeacherAttendance** (date, status, check_in, check_out) + `portal:teacher_attendance` (view/export). **Attendance** (student, date, status) + API to record by classroom; **no dedicated teacher UI** for “take class attendance.” **No lesson plan** model or submission flow. | Teacher UI to log student attendance for their classes; **Lesson plan** (or “lesson notes”) model + submit-for-approval workflow. |
| **3. Academic evaluation** | CA entry (Sequences 1–6), report card generation. | Marks entry (`evals:teacher_marks_entry`), OCR, CSV import, approval workflow, report generation. Sequences/terms in UI and reports. | Mostly covered; ensure “next” in workflow is clear (e.g. “Enter marks → Submit for approval → Published”). |
| **4. Communication & reporting** | Parent alerts (performance/conduct); generate/download/print report cards. | Department chat, announcements, class threads; parent contact requests. Reports: publish term results; parents see in portal. Teachers don’t “send report cards” directly—admin publishes. | Optional: “Alert parent” action from teacher (e.g. link to existing messaging or notification). Report cards: keep current flow (admin publish); teacher workflow can link to “View report card” or “Print” if permission exists. |
| **5. Performance & compliance** | Periodic teacher evaluation (attendance, student performance, timely reporting); principal review. | **No** teacher performance appraisal model. We have: TeacherAttendance, marks completion (widget), grade approval. | **Teacher performance snapshot** (for principal): attendance rate, marks completion, approval timeliness—read-only dashboard or report; optional formal **TeacherAppraisal** model later. |
| **6. Offboarding** | Exit: handover, final salary, archive. | TeacherProfile (is_active); TeacherPayRecord; TeacherLeaveRequest. No structured offboarding checklist or “exit” workflow. | Optional: **Offboarding checklist** (handover items, final pay, set is_active=False) or simple admin checklist. |

---

## 2. RBAC and permissions (keep everything compatible)

- **Role:** Teachers use existing `User.Role.TEACHER` and optional RBAC roles (e.g. HOD, DEPT_LEAD) where configured.
- **Access:** Every new view/action must:
  - Use `@role_required(User.Role.TEACHER)` (or equivalent) for teacher-only routes.
  - For teacher-scoped data: filter by `TeacherAssignment` (and thus subject_assignment → classroom/term/year) so teachers only see their classes.
- **Principals/Admin:** Performance view and “lesson plan approval” (if added) must be restricted to roles that can see all teachers (e.g. ADMIN, LEADERSHIP, PRINCIPAL) or by department (HOD).
- **Scale:** Avoid loading all teachers/students at once; use pagination, `select_related`/`prefetch_related`, and filters (e.g. by term, classroom, date range).

---

## 3. Teacher Workflow Center – proposed structure

Same idea as the admin Workflow Center: **steps** with **title**, **subtitle**, **progress_label**, **tip**, and **links**. Teacher sees only steps they’re allowed to access (RBAC). Progress labels come from real data (counts, percentages).

### Step 1) My profile & timetable  
- **Subtitle:** Onboarding, assignments, and schedule.  
- **Progress:** e.g. “Profile complete · 5 classes” (from TeacherAssignment count for active year).  
- **Tip:** “Ensure your profile and class assignments are up to date.”  
- **Links (existing):**  
  - Teacher hub (dashboard)  
  - Syllabus (`portal:portal_syllabus`)  
  - If timetable view exists: “My timetable”  
  - Optional: “Upload documents” (Document Library or profile)  
- **RBAC:** TEACHER only; data scoped to current user’s TeacherProfile and assignments.

### Step 2) Daily routine  
- **Subtitle:** Attendance (yours and your classes), lesson plans.  
- **Progress:** e.g. “Checked in today · 2/3 classes attendance done” (from TeacherAttendance today + student Attendance for teacher’s classrooms today).  
- **Tip:** “Check in when you arrive; take class attendance for each period.”  
- **Links (existing + new):**  
  - **Attendance** (your check-in/out) → `portal:teacher_attendance`  
  - **Take class attendance** (new) → teacher UI to mark student Present/Absent/Late for their classes (by date/period if needed).  
  - **Lesson plans** (new, optional) → list “My lesson plans” + “Submit new” → principal approval queue.  
- **RBAC:** TEACHER; class attendance filtered by teacher’s classrooms; lesson plans filtered by teacher.

### Step 3) Marks & sequences  
- **Subtitle:** Enter marks (Sequences 1–6), submit for approval, track status.  
- **Progress:** e.g. “78% entered · 12 pending” (reuse existing completion from teacher_dashboard).  
- **Tip:** “Enter CA for each sequence; submit for approval when ready.”  
- **Links (existing):**  
  - Enter marks → `evals:teacher_marks_entry`  
  - View marks → `evals:teacher_marks_list`  
  - Grade import / template  
  - Approval requests (if teacher can see their own) or “Marks status”  
- **RBAC:** Existing evals permissions (teacher sees only assigned subjects/classes).

### Step 4) Reports & communication  
- **Subtitle:** Report cards, parent communication, announcements.  
- **Progress:** e.g. “Term published” or “2 announcements” (from term publish status + optional count).  
- **Tip:** “After approval, admin publishes reports; use messages for parent alerts.”  
- **Links (existing):**  
  - Department chat → `communication:group_list`  
  - Create announcement → `communication:department_announcement_create`  
  - Parent contact requests → `portal:staff_contact_request_list` (if teacher has access)  
  - Optional: “Report cards” (link to report library or publish view if permitted).  
- **RBAC:** Existing communication/report permissions.

### Step 5) My attendance & pay  
- **Subtitle:** Your attendance record, pay history, leave.  
- **Progress:** e.g. “Present today · 3 leave requests” (from TeacherAttendance + TeacherLeaveRequest).  
- **Links (existing):**  
  - Attendance → `portal:teacher_attendance`  
  - Pay history → `portal:teacher_pay_history`  
  - Leave → `portal:teacher_leave`  
- **RBAC:** TEACHER only; only own records.

### Step 6) Performance (optional, for future)  
- **Subtitle:** Your attendance rate, marks completion, timely reporting (read-only).  
- **Progress:** e.g. “95% attendance · 100% marks submitted on time.”  
- **Links:**  
  - “My performance summary” (new view: aggregates from TeacherAttendance + evals completion + approval dates).  
- **RBAC:** TEACHER sees own; principal/admin sees all (separate view or same view with broader filter).

---

## 4. Progress “from center”: what you’ve done → where you are → what’s next

- **Hero / summary (top of Teacher Workflow Center):**  
  - Active year & term (same as admin).  
  - 3–4 badges: e.g. **Assignments** (count), **Marks completion** (%), **Today’s attendance** (Present/—), **Pending tasks** (e.g. “2 classes attendance”, “5 marks pending”).  
- **Steps:** Each step card shows:  
  - **progress_label:** e.g. “5 classes · 78% marks” so the teacher sees “where I am.”  
  - **tip:** Short “what’s next” (e.g. “Enter marks for Sequence 2” or “Take attendance for Form 5A”).  
- **Links:** Actions for “what’s next” (Enter marks, Take attendance, Submit lesson plan, etc.).  
- **Optional:** A small “This week” or “Today” list: e.g. “Take attendance Form 5A, Enter marks English Seq 2.”  
- All of this must be computed with **efficient queries** (e.g. one query per step, use existing `teacher_scope`, `progress` from teacher_dashboard).

---

## 5. Scale and flexibility (20,000+ users)

- **Queries:**  
  - Use `select_related` / `prefetch_related` for assignments, classrooms, terms.  
  - No unbounded `.all()` for teachers or students; always filter by year/term/classroom and paginate where appropriate.  
- **Indexes:** Ensure indexes on `TeacherAssignment`, `TeacherAttendance`, `Attendance`, `Evaluation` (e.g. by teacher, date, classroom, term)—already partially in place; add if new queries need them.  
- **Caching:** Consider short-lived cache (e.g. 1–5 min) for “workflow progress” counts per teacher if needed.  
- **Pagination:** Any list of students, classes, or lesson plans must be paginated (e.g. 20–50 per page).  
- **Configurability:** Keep steps and links **configurable** (e.g. feature flags or site settings) so schools can turn off “Lesson plans” or “Performance” without code change.

---

## 6. Implementation phases

### Phase A – Teacher Workflow Center (structure only, existing features)

- **Add view:** e.g. `teacher_workflow_center` (or extend teacher dashboard with a “Workflow” tab/section).  
- **URL:** e.g. `portal:teacher_workflow` or under `/portal/teacher/workflow/`.  
- **Template:** New template (e.g. `teacher/workflow_center.html`) **reusing the same layout pattern** as `accounts/workflow_center.html` (steps grid, cards, progress_label, tip, links) so it looks and feels comparable.  
- **Context:** Build `steps` list with the 5–6 steps above; each step’s `links` and `progress_label` use **only existing** URLs and existing data (assignments, progress, TeacherAttendance, leave count).  
- **RBAC:** View protected by `@role_required(User.Role.TEACHER)`; all data filtered by current teacher (teacher_scope, assignments).  
- **Deliverable:** Teachers see a Workflow Center with “what I’ve done / where I am / what’s next” using current features only (no lesson plans, no teacher performance appraisal yet).

### Phase B – Class attendance by teacher

- **Add view:** “Take class attendance” – teacher selects date (default today), then classroom (from their assignments), then sees student list and sets status (Present/Absent/Late/Excused).  
- **Backend:** Reuse `Attendance` model (student, date, status, optional teacher/classroom/term); ensure API or form saves with correct classroom/term.  
- **RBAC:** Only teacher’s assigned classrooms; filter by academic year/term.  
- **Link:** Add to Teacher Workflow Center Step 2 (Daily routine).  
- **Scale:** Paginate student list; bulk “Mark all present” + override per student.

### Phase C – Lesson plans (optional)

- **Model:** e.g. `LessonPlan` (teacher, subject_assignment or classroom, term, date/week, title, content or file, status: DRAFT / SUBMITTED / APPROVED / REVISIONS_REQUESTED).  
- **Teacher UI:** “My lesson plans” (list) + “Submit new” (form or upload). Submit for approval.  
- **Principal/Admin UI:** “Lesson plans to review” (filter by teacher/department/date); approve or request revisions.  
- **RBAC:** Teacher sees own; principal/admin/HOD see by permission.  
- **Link:** Add “Lesson plans” to Step 2 in Teacher Workflow Center.  
- **Progress:** e.g. “3 submitted this week · 1 pending approval.”

### Phase D – Teacher performance snapshot (optional)

- **View (read-only):** “My performance” for teacher: attendance rate (from TeacherAttendance), marks completion %, “submitted on time” (e.g. before deadline if we have deadlines).  
- **View (principal):** Same metrics per teacher (list); filter by department.  
- **RBAC:** Teacher sees own; principal/admin/HOD see all or by department.  
- **No new model required** for MVP; aggregate from existing tables. Optional later: `TeacherAppraisal` for formal reviews.  
- **Link:** Add Step 6 (Performance) to Teacher Workflow Center.

### Phase E – Offboarding (optional)

- **Lightweight:** Admin checklist (handover, final pay, set TeacherProfile.is_active = False).  
- **Or:** Simple “Offboarding” step for admin only (link to teacher list + “Archive” or “Deactivate”), not necessarily in Teacher Workflow Center.

---

## 7. Suggested order

1. **Phase A** – Teacher Workflow Center with existing features (fast, gives the “center” experience and progress).  
2. **Phase B** – Class attendance UI for teachers (high impact for daily use).  
3. **Phase C** – Lesson plans (if school wants digital submission and approval).  
4. **Phase D** – Teacher performance snapshot (improves accountability).  
5. **Phase E** – Offboarding as needed.

---

## 8. Files to add/touch (summary)

| Item | File(s) |
|------|--------|
| Teacher Workflow Center view | `apps/portal/views.py` or `apps/evals/views.py` (new view); or extend teacher_dashboard with a “Workflow” block. |
| Teacher Workflow Center template | `templates/teacher/workflow_center.html` (mirror structure of `accounts/workflow_center.html`). |
| Teacher Workflow URL | `apps/portal/urls.py` – e.g. `path("teacher/workflow/", teacher_workflow_center, name="teacher_workflow")`. |
| Sidebar / dashboard link | Add “Workflow” or “My workflow” to teacher sidebar and/or teacher dashboard hero. |
| Class attendance view | New view in `portal` or `academics`; form to select date/classroom and save Attendance records. |
| Lesson plan (Phase C) | New model (e.g. `apps/people/models.py` or `apps/academics`); admin + teacher list/submit + principal review. |
| Performance snapshot (Phase D) | New view(s) + optional small template; reuse TeacherAttendance, evals completion, approval data. |

---

## 9. Summary

- **Teacher Workflow Center** = same idea as admin Workflow Center: steps, progress labels, tips, links; all RBAC-compatible and scoped to the logged-in teacher.  
- **Progress “from the center”** = hero badges + per-step progress_label + tip so teachers see “what I’ve done → where I am → what’s next.”  
- Use **existing features** first (onboarding, attendance, marks, communication, pay, leave); add **class attendance UI**, then **lesson plans** and **performance snapshot** as needed.  
- Keep **scale in mind** (20k+ users): efficient queries, pagination, indexes, optional caching.  
- This plan aligns with your Cameroon teacher flow (onboarding, daily ops, sequences, communication, performance, offboarding) while staying within current RBAC and existing features where possible.
