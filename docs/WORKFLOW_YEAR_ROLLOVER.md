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
- **View:** `apps.accounts.views_rollover.clone_year_setup` (GET: form; POST: run clone, redirect to Workflow Center).

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
- On **Apply rollover** (synchronous path, `rollover_year`):
  - For each student, a **new `Enrollment`** is opened in the target year (`apps.people.enrollment_services.open_enrollment`) and the prior year's enrollment is **closed** with a recorded outcome — nothing is overwritten, so the leaving year survives as history. The legacy `StudentProfile.academic_year`/`classroom` fields are kept in step as a synchronised **projection** of the active enrollment (`apps.people.models.Enrollment.sync_student_row`), so the existing readers of `student.classroom` keep working.
  - A student sent to "— Graduate (Alumni) —" has their enrollment closed as `GRADUATED` (`graduate_student`) and is marked `status=ALUMNI`, `is_active=False`.
  - Optionally, **Lock source year** sets `AcademicYear.is_locked = True` on the source year **after** the move so further rollover from that year is refused. The lock is enforced at the **application layer** (view/service checks), not by a database constraint.

**Code**

- **Promotion status:** `apps.reports.services.get_promotion_status(student, academic_year, overall_average)` and `get_promotion_thresholds`; annual average from `_annual_average_for_student(student, terms)` in the same module.
- **View:** `apps.accounts.views_rollover.rollover_year` (GET: choose source/target, then show student table with suggested next class; POST: open/close enrollments and optional lock). The same module also hosts the queued proposal path — see §5.
- **Enrollment lifecycle:** `apps.people.enrollment_services.open_enrollment` / `graduate_student` / `outcome_for_manual_placement` — the one place a placement changes; each opens a new `apps.people.models.Enrollment` and closes the prior one.
- **Model:** `AcademicYear.is_locked` (when True, rollover from that year is blocked in the POST handler — an application-layer check, not a DB constraint).

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
| **apps.accounts.views_rollover.rollover_year** | Renders the student list with promotion status and next-class dropdowns; on POST, opens a new `Enrollment` per student and closes the prior one (`open_enrollment`), keeps `StudentProfile.academic_year`/`classroom` as a synced projection, and optionally sets `source_year.is_locked`. |
| **Workflow Center** | Links to “Clone previous year” and “Year-end rollover” so operators can run both from one place. |

So: **clone** prepares the next year’s structure; **rollover** moves students into that year and assigns their next class, with promotion status and optional year lock.

---

## 4. Rollover enhancements

- **Pre-rollover checklist:** When source and target years are selected, a checklist is shown: source year not locked, target year has classrooms, and a reminder to finalize grades and reports.
- **Graduate (Alumni):** In the "Next class" dropdown, choosing "— Graduate (Alumni) —" marks the student as alumni (status ALUMNI, is_active False, classroom null) instead of assigning a classroom.
- **Promotion-level mapping:** Model `ClassroomPromotionMapping` (Workflow → Year setup → Promotion mapping) maps (source year, source classroom) to (target year, target classroom). The rollover wizard uses these to suggest the next class (e.g. Form 5A → Lower Sixth A).
- **Notify parents after rollover:** Checkbox on the rollover form creates an in-app notification for each guardian of each rolled-over student (and optionally SMS if the guardian has phone and receives_sms). Both the synchronous and the queued (§5) apply paths send the same notifications.

---

## 5. Queued rollover (proposal → approve → apply)

Besides the single-request "Apply rollover" above, the same screen can enqueue the move as a reviewable **proposal** so a large cohort is processed asynchronously:

1. **Prepare** — `apps.accounts.views_rollover.rollover_prepare` (POST `/authentication/workflow/rollover/prepare/`) runs `apps.accounts.tasks.prepare_rollover_proposal`, which creates a `RolloverProposal` in status **`PENDING`** with one `RolloverProposalItem` per active student (suggested next class, promotion status, outstanding-returns count).
2. **Review & approve** — `apps.accounts.views_rollover.rollover_proposal_detail` (`/authentication/workflow/rollover/proposal/<id>/`) lets the operator adjust each item's approved next class / graduate flag, then **Approve** moves the proposal to **`APPROVED`**.
3. **Apply** — approving unlocks an **Apply** action that enqueues `apps.accounts.tasks.apply_rollover_proposal` (Celery via `apply_async`, falling back to in-process `apply` when no broker is available). The task opens/closes enrollments exactly like the synchronous path (`open_enrollment` + `graduate_student`), marks the proposal **`APPLIED`**, optionally locks the source year, and — when **Notify parents** was ticked — notifies each rolled student's guardians. The queue of PENDING/APPROVED proposals is at `apps.accounts.views_rollover.rollover_queue` (`/authentication/workflow/rollover/queue/`).

Lifecycle: `RolloverProposal.Status` = `PENDING` → `APPROVED` → `APPLIED` (or `CANCELLED`).

---

## 6. Pre-rollover backup gate (M29 / EOY gap #3)

Rollover is **destructive** — it opens a new enrollment for every active student in the target year, closes the source-year enrollment, can graduate students to ALUMNI, and can lock the source year. If the operator picked the wrong source/target years or a bad promotion mapping, the whole cohort has already moved before anyone notices. The safety net is the **M28 tenant DR snapshot** — a signed, encrypted, immutable full-state export of the tenant.

**The gate.** Both apply paths refuse to move any student unless **either**:

1. a **recent M28 snapshot** exists for the school (a `apps.lifecycle.models_dr_snapshot.TenantImmutableSnapshot` row — the same row `apps.lifecycle.tenant_dr_snapshot.capture_daily_snapshot` writes and the daily `lifecycle.capture_tenant_immutable_snapshots_daily` Celery task drives — with `created_at` within the freshness window, default **7 days**, overridable via `settings.RMC_PRE_ROLLOVER_BACKUP_MAX_AGE_DAYS`); **or**
2. the operator **explicitly overrides** by acknowledging there is no backup (form checkbox `acknowledge_no_backup`).

The M28 snapshot is a **whole-tenant** artifact (school + `snapshot_date` + `created_at`); it is **not** scoped to a single academic year, so the gate keys on **school + recency** only. `source_year` is passed only for the audit line.

**Code**

- **Gate helper:** `apps.accounts.rollover_backup.require_pre_rollover_backup(school, source_year, *, override=False, created_by=None)` — raises `django.core.exceptions.ValidationError` when neither a recent snapshot nor an override is present, and emits a PII-free audit line (`branch=backup-present` / `operator-override` / `refused-no-backup`, ids only). Companion reads: `recent_backup_exists(school, *, within_days=None)`.
- **Sync path:** `apps.accounts.views_rollover.rollover_year` (POST apply branch) — reads `acknowledge_no_backup`; a refusal shows a `messages.error` and re-renders **before** any student is moved.
- **Async path:** `apps.accounts.tasks.apply_rollover_proposal` threads `override_backup_gate` (default `False`) into `_apply_rollover_proposal_impl`, which calls the gate right after the APPROVED check and **before** the move loop; a refusal returns `{"ok": False, "error": …}` and leaves the proposal APPROVED (unapplied). `created_by` is derived from `proposal.approved_by or proposal.created_by`. `rollover_proposal_detail`'s **Apply** action also fails the gate in-request (rather than enqueueing a task that would silently refuse) and forwards the override.

**"Back up now" affordance**

- The operator creates the required backup by running the existing **M28 tenant DR snapshot** flow. `apps.accounts.rollover_backup.create_pre_rollover_backup(school)` is a thin, read-only delegate to `capture_daily_snapshot(school)`; the `rollover_year` POST branch triggers it when `create_backup_now` is present (reuses the existing `accounts:rollover_year` URL — no new route). Adding the button + the `acknowledge_no_backup` checkbox to `templates/accounts/rollover_year.html` (and the proposal-detail Apply form) is the remaining UI wiring. Absent a manual trigger, the daily snapshot task already produces a fresh backup for every active school.
