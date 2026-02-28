# Wave 5 — Scheduling & SOW

| Sub-item | Description | Status |
|----------|-------------|--------|
| W5-1 | Drag-drop scheduler UI | Roadmap |
| W5-2 | Conflict checks (time/room) | ✅ |
| W5-3 | Abbreviated day support | Roadmap |
| W5-4 | Recurring events | Roadmap |
| W5-5 | Live timeline view | Roadmap |
| W5-6 | Shift/push SOW (syllabus) when day canceled | Roadmap |

## Current implementation

### Models and generator (`apps/academics/scheduling.py`)

- **Room** — Physical rooms (classroom, lab, gym, etc.), capacity, facilities.
- **TimeSlot** — Day of week + start/end time, slot name, active flag.
- **TeacherAvailability** — Which time slots a teacher is available.
- **Schedule** — Master schedule per academic year/term (Draft / Published / Archived).
- **ScheduleEntry** — Classroom, subject, teacher, room, time_slot; `clean()` validates no teacher/room double-booking for same slot.
- **SchedulingConstraint** — Optional constraints for the generator.
- **TimetableGenerator** — `generate_schedule()`, `detect_conflicts(schedule)`, `optimize_schedule(schedule)`.

Conflict detection finds:

- **TEACHER_CONFLICT** — Same teacher, same time_slot, multiple entries.
- **ROOM_CONFLICT** — Same room, same time_slot, multiple entries.

### Conflict-check API (W5-2)

- **Endpoint:** `GET /api/schedules/<schedule_id>/conflicts/`
- **Auth:** IsAuthenticated; schedule must belong to current school (via `academic_year.school`).
- **Response:** `{ "schedule_id", "schedule_name", "conflicts": [...], "has_conflicts": bool }`. Each conflict has `type`, `teacher` or `room`, `time_slot`, `entries` (list of ScheduleEntry PKs).
- **Code:** `apps/academics/api_views.py` — `ScheduleConflictsAPI`; URL in `apps/api/urls.py` as `schedule-conflicts`.

### Teacher timetable

- **View:** `portal:teacher_timetable` — shows a teacher’s schedule (Schedule + ScheduleEntry).
- **URLs:** See `apps/portal/urls.py` and `apps/academics/urls.py` (syllabus routes only; no schedule CRUD in academics URLs yet).

## Roadmap (not yet implemented)

- **W5-1 Drag-drop scheduler UI** — Admin/portal UI to build or edit schedules by dragging classes to slots; call generator or save entries; use conflict API before save/publish.
- **W5-3 Abbreviated day** — Model or config for reduced time slots on certain days (e.g. early dismissal); generator and UI to respect abbreviated slots.
- **W5-4 Recurring events** — Recurring non-class events (meetings, assemblies) that consume room/time_slot and appear in conflict checks and timeline.
- **W5-5 Live timeline view** — Per-day or per-room timeline of entries (and recurring events) for a given schedule.
- **W5-6 Shift/push SOW** — When a day is canceled (e.g. snow day), bulk shift syllabus “planned vs actual” dates (SOW) and optionally reschedule affected entries; document in syllabus/SOW docs.

## Code refs

- `apps/academics/scheduling.py` — Room, TimeSlot, Schedule, ScheduleEntry, TimetableGenerator, `detect_conflicts()`.
- `apps/academics/api_views.py` — `ScheduleConflictsAPI`.
- `apps/api/urls.py` — `path('schedules/<int:schedule_id>/conflicts/', ...)`.
- `apps/portal/views.py` — `teacher_timetable`.
- Standards: S7 (Scheduler REST API generate/validate) — validate covered by this conflict API; generate remains backend-only for now.
