# Workflow & Dashboard Enhancements Summary

**Date:** January 28, 2026  
**Status:** Complete

---

## 1. Workflow Center Enhancements

### Progress indicators
- **`_workflow_progress(year)`** in `apps/accounts/views.py`:
  - Returns counts for **classrooms**, **students**, **teachers** for the active year.
  - Used to show progress in the Workflow Center hero (badges: Classrooms, Students, Teachers).
  - Used to build **recommended next steps** on the backend dashboard.

### Workflow Center template
- **Breadcrumbs:** Backend → Workflow Center.
- **Progress summary:** Hero shows badges (e.g. "Classrooms: 5", "Students: 120", "Teachers: 12").
- **Step progress labels:** Each step can show a short status (e.g. "12 students, 8 teachers" for Onboarding).
- **Primary actions:** "Add student" and "Add teacher" are primary (solid) buttons when backend people UI is used.
- **Documents & forms step:** New step **"5b) Documents & forms"** with:
  - Document library
  - Signature requests
  - Public documents
- **Step numbering:** Settings & theme is now **"7) Settings & theme"**; Certification remains **"6)"**.

### Backend vs admin links
- Workflow Center prefers **backend UI** links when available:
  - **Add student** → `accounts:backend_student_create` (or admin add).
  - **Add teacher** → `accounts:backend_teacher_create` (or admin add).
  - **Student list** → `accounts:backend_student_list` (or admin changelist).
- If backend people URLs are missing (e.g. import error), the view falls back to admin URLs.

---

## 2. Backend Dashboard Enhancements

### Recommended next steps
- **Widget:** `templates/components/recommended_next_steps.html`.
- **Context:** `recommended_next_steps` (list of `{label, url, icon}`).
- **Logic in view:**
  - No active year → suggest "Set up academic year".
  - Year but 0 classrooms → "Create classrooms".
  - Year but 0 students → "Add student" (backend or admin).
  - Year but 0 teachers → "Add teacher" (backend or admin).
  - If nothing missing → "Workflow Center" and "Publish results".
- **Placement:** Directly under the welcome header, above finance alerts.

### Quick Actions
- **Add Student** and **Add Teacher** now point to backend UI when available:
  - `accounts:backend_student_create` / `accounts:backend_teacher_create`.
  - Fallback to `admin:people_studentprofile_add` and `admin:people_teacherprofile_add` when `use_backend_people_ui` is False.
- **Onboard Student (wizard)** and **Onboard Teacher (wizard)** kept as separate actions.

### Breadcrumbs
- **Context:** `BREADCRUMBS` for `partials/breadcrumbs.html`:
  - `Backend` → backend dashboard.
  - `Dashboard` (current, active).
- **Also:** `breadcrumbs` (for any component using that key).

### Context variables added
- `workflow_progress` – from `_workflow_progress(year)`.
- `recommended_next_steps` – list of suggested actions.
- `use_backend_people_ui` – whether backend people URLs exist (so templates can choose backend vs admin links).
- `BREADCRUMBS` – for portal breadcrumb partial.

---

## 3. Files Touched

| File | Change |
|------|--------|
| `apps/accounts/views.py` | `_workflow_progress()`, workflow_center steps + progress, backend_dashboard context (workflow_progress, recommended_next_steps, use_backend_people_ui, BREADCRUMBS), NoReverseMatch import |
| `templates/accounts/workflow_center.html` | Breadcrumbs, progress summary, step progress_label, primary links, Documents step |
| `templates/accounts/backend_dashboard.html` | Include recommended_next_steps, Quick Actions use backend_student_create/backend_teacher_create with fallback |
| `templates/components/recommended_next_steps.html` | New widget |

---

## 4. User impact

- **Workflow Center:** Clear progress (classrooms/students/teachers), one place for documents & signatures, and prominent “Add student” / “Add teacher” that use the backend UI when available.
- **Backend dashboard:** “Recommended next steps” guide the next action (year setup, classrooms, students, teachers, or workflow/publish). Quick Actions use the same backend forms when available.
- **Breadcrumbs:** Backend and Workflow Center pages have consistent breadcrumbs (Backend → Dashboard / Workflow Center).

---

## 5. Optional follow-ups

- Teacher list/create and classroom create templates (if not already present).
- Parent dashboard “next step” when children are linked (e.g. “View report cards” or “Pending signatures”).
- Workflow step completion flags (e.g. “Year setup ✓”) from real data.
