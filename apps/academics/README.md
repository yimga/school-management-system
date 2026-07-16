# apps/academics

> The academic backbone: year/term/class/subject structure, attendance,
> timetabling, the lesson-and-homework LMS, discipline, and degree audit.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 46 models · 68 migrations · 34 test modules · ~24.5k LOC

## What this app owns

Academics is the app almost every other app reads from. It owns the calendar
spine (`AcademicYear` → `Term` → `InstructionDay`), the org structure
(`Department`, `Specialty`, `Classroom`, `Subject`, and the recursive
`AcademicStructureNode` tree), the join that makes teaching real
(`SubjectAssignment` = class + subject + teacher + term), daily `Attendance`,
the generated timetable, classroom LMS work, discipline, and — for
higher-education tenants — degree programs, transfer credit, and certification
exam sessions. If a concept is "what the school teaches, to whom, when", it
lives here.

The most important thing to know before touching it is a **deployment reality
documented in `scheduling_solver.py`**: `ortools` is intentionally absent from
`requirements.txt`, so in every deployed environment `_ortools_available()`
returns `False` and the CP-SAT path never runs. The real, wired production
solver behind `generate_timetable_with_solver` — the one the Celery task, the
`solve_timetable` command, and the REST endpoint actually execute — is the
Django-model CSP generator `apps.academics.scheduling.TimetableGenerator.generate_schedule`.
The CP-SAT code is dormant-by-default rather than dead: it activates only if an
operator installs `ortools` themselves.

The second recurring pattern is **new capability without new migrations**. The
lesson/homework kernel, the JSON workflow config, and proximity attendance all
deliberately reuse existing storage (`School.settings` JSON buckets, or the
existing `Attendance` row) rather than adding tables.

## Key models

The 15 that matter most, of 46 declared. This table is not exhaustive.

| Model | Table | Purpose |
| --- | --- | --- |
| `AcademicYear` | `academics_academicyear` | The calendar spine every other row hangs off. |
| `Term` | `academics_term` | Term within a year; the uniqueness key most scheduling constraints use. |
| `Classroom` | `academics_classroom` | A class group of students (not a physical room — see `Room`). |
| `Subject` | `academics_subject` | Taught subject; carries `credits`, consumed by degree audit. |
| `SubjectAssignment` | `academics_subjectassignment` | The central join: class + subject + teacher + term/year. |
| `AcademicStructureNode` | `academics_academicstructurenode` | Recursive academic org tree under a School, provisioned from a country pack. |
| `Attendance` | `academics_attendance` | Per-day student attendance; roll call and parent absence alerts. |
| `Schedule` / `ScheduleEntry` | `academics_schedule` / `academics_scheduleentry` | The generated master timetable and its individual sessions. |
| `Room` / `TimeSlot` | `academics_room` / `academics_timeslot` | Physical facilities and the predefined slots the solver places into. |
| `SchedulingConstraint` / `TeacherAvailability` | `academics_schedulingconstraint` / `academics_teacheravailability` | Solver inputs. |
| `LMSAssignment` / `LMSSubmission` | `academics_lmsassignment` / `academics_lmssubmission` | A unit of work assigned to one classroom, and one student's response. |
| `Incident` | `academics_incident` | Disciplinary incident; alerts parents when `notify_parent` is set. |
| `RestorativeAction` / `BehaviorPointLedger` | `academics_restorativeaction` / `academics_behaviorpointledger` | Restorative follow-up and cumulative behavior points. |
| `CurriculumStandard` / `CurriculumNode` | `academics_curriculumstandard` / `academics_curriculumnode` | Country-agnostic standard and its Subject > Unit > Topic hierarchy. |
| `DegreeProgram` / `StudentDegreeEnrollment` / `TransferCredit` | `academics_degreeprogram` / `academics_studentdegreeenrollment` / `academics_transfercredit` | Higher-ed degree audit inputs; `requirements_json` defines required courses/credits/milestones. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `run_scheduling_solver_task` | The app's only registered task; runs `TimetableGenerator`, not CP-SAT. |
| Command | `solve_timetable` | Same generator, synchronous. |
| Command | `run_auto_promotion`, `fix_term_positions` | Year rollover / term ordering. |
| Command | `import_curriculum_nodes`, `export_certification_pack` | Curriculum import, certification pack export. |
| Command | `seed_demo`, `seed_testdata_2425`, `seed_buea_synthetic` | Fixtures. |
| URLs | `timetable_generate` / `timetable_review` / `timetable_publish` | The persisting Stack-A flow — the in-product timetable surface. |
| URLs | `syllabus_builder`, `syllabus_submit` / `syllabus_approve` / `syllabus_reject`, `syllabus_approval_queue`, `teacher_syllabus_hub`, `ca_marks_input`, `workflow_wizard` | |
| Module | `scheduling` (`TimetableGenerator`) | The live solver. |
| Module | `scheduling_solver` | Dormant CP-SAT path (requires operator-installed `ortools`). |
| Module | `timetable_solver` | Separate standalone in-memory backtracking solver kept for its unit tests. |
| Module | `lesson_homework_kernel`, `curriculum_map`, `degree_audit`, `year_close`, `schema_repair`, `proximity_attendance` | |

## Before you change this

- **There are three "solvers" and only one of them runs.** `apps.academics.scheduling.TimetableGenerator`
  is production. `scheduling_solver`'s CP-SAT model is dormant unless someone
  installs `ortools`. `timetable_solver` is a *separate* standalone in-memory
  backtracking solver kept for its unit tests, and it is explicitly **not** the
  fallback for `scheduling_solver` — its JSON-console view was retired when the
  product converged on the generate/review/publish flow. Fixing a timetable bug in
  the wrong module is the single easiest mistake to make in this app.
- **Regenerating a timetable must delete ALL schedules for the term, draft AND
  published.** The DB uniqueness constraints key on (term, teacher/room, time_slot)
  with condition `is_cancelled=False` and are **status-agnostic**, so a surviving
  `PUBLISHED` schedule's entries raise `IntegrityError` (a live 500) the moment the
  generator re-places the same slot. Regenerate means replace the term's timetable
  (`e159560a8`).
- **`Attendance.school` is backfilled in `save()`, and that is the only chokepoint.**
  Several create paths (teacher roll-call, mobile sync, REST record) omit `school`,
  so `save()` derives it from the student, falling back to the classroom. A row with
  `school=NULL` silently escapes every school-scoped consumer *and* survives a
  tenant's permanent delete as orphan student PII. Therefore: **never create or
  update attendance via `queryset.update()` or `bulk_create()`** — both bypass
  `save()` and reintroduce the exact defect the chokepoint closes (`9a654c9e4`).
- **`Classroom` is a class group; `Room` is a physical space.** They are different
  models and the timetable joins both. Reading one where you meant the other
  type-checks fine and produces nonsense.
- **The lesson/homework kernel ships zero migrations on purpose.** State lives in
  `School.settings["academics"]["lesson_plans" | "homeworks" | "homework_submissions"]`,
  each bucket FIFO-capped at 2000 entries. Do not go looking for a `Homework` table
  — it does not exist. `submit_student_work` records a submission *without* changing
  the homework's own stage.
- **`proximity_attendance` deliberately reuses `academics.Attendance`.** A BLE/RFID/NFC/QR
  ping normalises into a standard attendance record routed through the offline queue
  (`action_type=ATTENDANCE`), so it drains on reconnect exactly like the manual path.
  The proximity nature is carried in the payload and `remarks` — no new model, and the
  platform never assumes a specific radio.
- **`curriculum_map` is pure Python with no DB writes** so it is safe to import from
  signal handlers and tasks. School overrides at
  `School.settings["academics"]["curriculum_map"][<subject>]` win over the shipped
  defaults.
- **`schema_repair` exists because of django-tenants drift.** Before hand-rolling a
  column fix, check `migrate --plan` for an existing repair step — the platform-wide
  pattern is an idempotent introspect-and-add rather than an explicit model list.
