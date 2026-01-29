# How Academic Year Rollover Works

This document describes how the system supports **rolling over** from one academic year to the next: preparing the next year’s structure and moving students into it.

---

## Two parts: Clone year vs Rollover

| Step | Purpose | Where |
|------|--------|--------|
| **Clone previous year** | Copy **structure** (terms, classrooms, subject assignments, promotion rules) from an existing year into the **next** year. Does not move students. | Workflow Center → Year setup → “Clone previous year” → `/authentication/workflow/clone-year/` |
| **Year-end rollover** | Move **students** from the current (source) year to the next (target) year and assign each to a classroom in the target year. Optionally lock the source year. | Workflow Center → “Year-end rollover” → `/authentication/workflow/rollover/` |

---

## 1. Clone previous year

**What it does**

- **Source year** and **target year** are chosen by the operator (both must already exist; create the target year in Admin → Academic years first).
- The system copies:
  - **Terms** (name, position, custom label, start/end dates) from source to target.
  - **Classrooms** (name, department, allows_third_term) into the target year. Classroom **codes** are made unique by appending a year suffix (e.g. `F5A` → `F5A-2526` for year 2025/2026).
  - **Subject assignments** (term, classroom, specialty, subject, coefficient) into the target year, using the new terms and classrooms.
  - **Promotion rules** (promotion_average, demotion_average) for the target year, mapped to the new classrooms where applicable.

**Code**

- **Service:** `apps.academics.services_year_setup.clone_academic_year(from_year, to_year, ...)`.
- **View:** `accounts.views.clone_year_setup` (GET: form; POST: run clone, redirect to Workflow Center).

**Typical use**

- Before or at the start of a new academic year: clone the **previous** year (e.g. 2024/2025) into the **new** year (e.g. 2025/2026) so you have terms, classes, and subject setup ready. Then enrol students into the new year as usual, or use rollover to move them.

---

## 2. Year-end rollover

**What it does**

- Operator selects **source year** (e.g. 2024/2025) and **target year** (e.g. 2025/2026).
- The system lists all **active students** in the source year with:
  - Current classroom
  - **Annual average** (computed from evaluations across the source year’s terms)
  - **Promotion status** (PROMOTED / REPEAT / DEMOTED / NO_DATA) using `PromotionRule` for that year (e.g. promote ≥ 10/20).
  - A **suggested next class**: same **name** as current class in the target year (e.g. “Form 5A” → “Form 5A” in 2025/2026). If no match, first classroom in target year is suggested.
- Operator can change the “next class” per student (e.g. promoted students to “Upper Six A”, repeating to “Form 5A” in target year).
- On **Apply rollover**:
  - Each student’s `academic_year` is set to the target year and `classroom` to the chosen classroom.
  - Optionally, **Lock source year** sets `AcademicYear.is_locked = True` for the source year so no further grade edits or rollover from that year are intended.

**Code**

- **Promotion status:** `apps.reports.services.get_promotion_status(student, academic_year, overall_average)` and `get_promotion_thresholds`; annual average from `_annual_average_for_student(student, terms)` in the same module.
- **View:** `accounts.views.rollover_year` (GET: choose source/target, then show student table with suggested next class; POST: apply updates and optional lock).
- **Model:** `AcademicYear.is_locked` (when True, rollover from that year is blocked in the POST handler).

**Typical use**

- At **year end**: after publishing reports and finalising grades, run rollover from the **ending** year to the **next** year. Ensure the target year already has classrooms (e.g. from “Clone previous year”). Adjust next class for promoted vs repeating students if your “next level” class names differ (e.g. Form 5 → Upper Six). Optionally lock the source year after rollover.

---

## 3. How the code supports rollover end-to-end

| Piece | Role |
|-------|------|
| **AcademicYear** | `is_locked`: prevents rollover from and edits to a closed year. |
| **PromotionRule** | Per-year (and optional per-classroom) promotion/demotion thresholds (e.g. 10/20). Used to compute PROMOTED / REPEAT / DEMOTED. |
| **reports.services** | `get_promotion_status()`, `_annual_average_for_student()`, `terms_for_student()`: drive the rollover table and suggestions. |
| **academics.services_year_setup** | `clone_academic_year()`: builds the next year’s terms, classrooms, subject assignments, and promotion rules so the target year is ready for rollover. |
| **accounts.views.rollover_year** | Renders the student list with promotion status and next-class dropdowns; on POST, updates `StudentProfile.academic_year` and `StudentProfile.classroom` and optionally sets `source_year.is_locked`. |
| **Workflow Center** | Links to “Clone previous year” and “Year-end rollover” so operators can run both from one place. |

So: **clone** prepares the next year’s structure; **rollover** moves students into that year and assigns their next class, with promotion status and optional year lock.

---

## 4. Rollover enhancements

- **Pre-rollover checklist:** When source and target years are selected, a checklist is shown: source year not locked, target year has classrooms, and a reminder to finalize grades and reports.
- **Graduate (Alumni):** In the "Next class" dropdown, choosing "— Graduate (Alumni) —" marks the student as alumni (status ALUMNI, is_active False, classroom null) instead of assigning a classroom.
- **Promotion-level mapping:** Model `ClassroomPromotionMapping` (Workflow → Year setup → Promotion mapping) maps (source year, source classroom) to (target year, target classroom). The rollover wizard uses these to suggest the next class (e.g. Form 5A → Lower Sixth A).
- **Notify parents after rollover:** Checkbox on the rollover form creates an in-app notification for each guardian of each rolled-over student (and optionally SMS if the guardian has phone and receives_sms).
