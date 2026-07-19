"""
Phase 9 (+ v2.90): OR-tools timetabling solver.

DEPLOYMENT REALITY — READ THIS FIRST
------------------------------------
``ortools`` is NOT a declared dependency of this project (it is intentionally
absent from ``requirements.txt``; the opt-in pin lives in
``requirements_optional.txt``), so in every deployed environment
``_ortools_available()`` returns ``False`` and the CP-SAT path
(``_solve_with_ortools``) DOES NOT RUN. The real, wired production solver for
``generate_timetable_with_solver`` is the Django-model CSP generator
``apps.academics.scheduling.TimetableGenerator.generate_schedule`` — that is
what the Celery task, the ``solve_timetable`` management command, and the v1
REST endpoint actually execute today.

The CP-SAT code below is kept as a real, ready implementation that activates
ONLY if an operator deliberately installs ``ortools`` (for example
``pip install -r requirements_optional.txt``). It is dormant-by-default, not
dead theater: when ortools is absent ``generate_timetable_with_solver``
transparently and intentionally uses ``TimetableGenerator``. (Note:
``apps.academics.timetable_solver`` is a SEPARATE, standalone in-memory
backtracking solver kept for its unit tests; its JSON-console view was retired
when the in-product timetable surface converged onto the persisting Stack-A
generate/review/publish flow. It is NOT the fallback for this module.)

Constraint set the CP-SAT model enforces WHEN ortools is installed (hard,
fail-if-violated):
  1. Each demand assigned exactly once
  2. Each (slot, room) holds at most one demand
  3. Same teacher cannot be in two slots simultaneously
  4. Same classroom (cohort) cannot be in two subjects simultaneously
  5. Teacher cannot be assigned to a `TeacherAvailability(is_available=False)` slot
  6. Room capacity must meet classroom student count (drops infeasible rooms)

Soft objective (maximised, ortools path only):
  Sum of `TeacherAvailability.preference_level` (1-10, default 5) across all
  picked (demand, slot) pairs. The solver picks among feasible solutions the
  one that respects teachers' stated slot preferences most heavily.
"""

from __future__ import annotations

import importlib.util
import logging
from typing import Optional

from .scheduling import TimetableGenerator, Schedule

logger = logging.getLogger("apps.academics.scheduling_solver")


def _ortools_available() -> bool:
    """Return True if ortools.sat.python.cp_model is importable.

    Hardened against Python 3.14: ``importlib.util.find_spec`` now raises
    ``ModuleNotFoundError`` for top-level packages that aren't installed,
    where older versions returned ``None``. Any exception means "not
    available", same effective outcome.
    """
    try:
        return importlib.util.find_spec("ortools.sat.python.cp_model") is not None
    except (ModuleNotFoundError, ImportError, ValueError):
        return False


def generate_timetable_with_solver(
    academic_year,
    term,
    created_by,
    use_ortools: bool = True,
) -> Schedule:
    """
    Generate a timetable.

    If ``use_ortools=True`` AND ``ortools`` is actually installed, the CP-SAT
    solver runs. In the project's default deployment ortools is NOT installed
    (see module docstring), so this transparently uses the real production
    solver ``TimetableGenerator`` (Django-model CSP). The fallback is the
    intended behavior, not an error path — hence the explicit ``logger.info``
    rather than a silent pass.
    """
    try:
        if use_ortools and _ortools_available():
            # Build a minimal CP-SAT model: assign (classroom, subject) to (room, slot) with no conflicts.
            schedule = _solve_with_ortools(academic_year, term, created_by)
            if schedule is not None:
                return schedule
        elif use_ortools:
            logger.info(
                "scheduling_solver ortools requested but not installed — "
                "using TimetableGenerator (CSP). Install ortools to enable CP-SAT."
            )
    except ImportError:
        # ortools disappeared between the find_spec probe and import — same
        # honest outcome: fall back to the wired CSP generator.
        logger.info(
            "scheduling_solver ortools import failed at solve time — "
            "using TimetableGenerator (CSP)."
        )
    gen = TimetableGenerator(academic_year=academic_year, term=term)
    return gen.generate_schedule(created_by=created_by)


def _solve_with_ortools(academic_year, term, created_by) -> Optional[Schedule]:
    """Use OR-Tools CP-SAT to assign classes to (room, time_slot). Returns Schedule or None.

    Only callable when ortools is installed. ``generate_timetable_with_solver``
    gates this behind ``_ortools_available()``; calling it directly without
    ortools present raises ``ImportError`` explicitly (no silent no-op) so the
    dormant path can never masquerade as having run.
    """
    if not _ortools_available():
        raise ImportError(
            "ortools is not installed; _solve_with_ortools cannot run. "
            "Use generate_timetable_with_solver(), which falls back to "
            "TimetableGenerator (the wired CSP solver), or install ortools."
        )
    from apps.academics.models import SubjectAssignment
    from apps.evals.models import TeacherAssignment
    from .scheduling import (
        Schedule,
        ScheduleEntry,
        Room,
        TeacherAvailability,
        TimeSlot,
    )

    time_slots = list(
        TimeSlot.objects.filter(is_active=True).order_by("day_of_week", "start_time")
    )
    rooms = list(Room.objects.filter(is_available=True).order_by("capacity"))

    if not time_slots or not rooms:
        return None

    # Build list of (classroom, subject, teacher_user) from SubjectAssignment + TeacherAssignment
    demands = []
    # tenant-isolation-allow: scoped via academic_year + term FKs (both tenant-bound; solver receives pre-scoped objects)
    subject_assignments = SubjectAssignment.objects.filter(
        academic_year=academic_year,
        term=term,
    ).select_related("classroom", "subject")
    for sa in subject_assignments:
        ta = (
            # tenant-isolation-allow: scoped via subject_assignment FK + academic_year FK (tenant-bound)
            TeacherAssignment.objects.filter(
                subject_assignment=sa,
                academic_year=academic_year,
                is_active=True,
            )
            .select_related("teacher__user")
            .first()
        )
        if ta and ta.teacher and getattr(ta.teacher, "user", None):
            demands.append((sa.classroom, sa.subject, ta.teacher.user))

    if not demands:
        return None

    cp_model = __import__(
        "ortools.sat.python.cp_model", fromlist=["cp_model"]
    ).cp_model

    # Load teacher availability for all teachers in the demand set.
    # Map: teacher_id -> {time_slot_id -> (is_available, preference_level)}
    teacher_ids = {d[2].id for d in demands}
    teacher_avail: dict[int, dict[int, tuple[bool, int]]] = {}
    avail_rows = TeacherAvailability.objects.filter(
        teacher_id__in=teacher_ids
    ).values("teacher_id", "time_slot_id", "is_available", "preference_level")
    for row in avail_rows:
        teacher_avail.setdefault(row["teacher_id"], {})[row["time_slot_id"]] = (
            bool(row["is_available"]),
            int(row["preference_level"]),
        )

    # Classroom sizes (default to 30 when relation unavailable / cohort empty).
    default_cohort_size = 30
    classroom_sizes: dict[int, int] = {}
    for classroom, _subj, _teacher in demands:
        if classroom.id in classroom_sizes:
            continue
        if hasattr(classroom, "students"):
            try:
                classroom_sizes[classroom.id] = (
                    classroom.students.count() or default_cohort_size
                )
            except (AttributeError, TypeError):
                classroom_sizes[classroom.id] = default_cohort_size
        else:
            classroom_sizes[classroom.id] = default_cohort_size

    model = cp_model.CpModel()
    num_demands = len(demands)
    num_slots = len(time_slots)
    num_rooms = len(rooms)

    # x[d, s, r] = 1 if demand d is in slot s and room r
    x = {}
    for d in range(num_demands):
        for s in range(num_slots):
            for r in range(num_rooms):
                x[(d, s, r)] = model.NewBoolVar(f"x_{d}_{s}_{r}")

    # Hard 1: Each demand assigned exactly once
    for d in range(num_demands):
        model.Add(
            sum(x[(d, s, r)] for s in range(num_slots) for r in range(num_rooms)) == 1
        )

    # Hard 2: Each (slot, room) at most one demand
    for s in range(num_slots):
        for r in range(num_rooms):
            model.Add(sum(x[(d, s, r)] for d in range(num_demands)) <= 1)

    # Hard 3: Teacher conflict — same teacher not in two places in same slot
    for s in range(num_slots):
        for d1 in range(num_demands):
            for d2 in range(d1 + 1, num_demands):
                if demands[d1][2].id == demands[d2][2].id:
                    model.Add(
                        sum(x[(d1, s, r)] for r in range(num_rooms))
                        + sum(x[(d2, s, r)] for r in range(num_rooms))
                        <= 1
                    )

    # Hard 4: Classroom conflict — a single cohort cannot be in two subjects
    # in the same slot (regardless of room/teacher).
    for s in range(num_slots):
        for d1 in range(num_demands):
            for d2 in range(d1 + 1, num_demands):
                if demands[d1][0].id == demands[d2][0].id:
                    model.Add(
                        sum(x[(d1, s, r)] for r in range(num_rooms))
                        + sum(x[(d2, s, r)] for r in range(num_rooms))
                        <= 1
                    )

    # Hard 5: Teacher unavailability — forbid any (demand, slot, *) where the
    # teacher of `demand` is marked unavailable for `slot`.
    forbidden_teacher_slots = 0
    for d_idx, (_, _, teacher) in enumerate(demands):
        avail_for_teacher = teacher_avail.get(teacher.id, {})
        for s_idx, slot in enumerate(time_slots):
            is_avail, _pref = avail_for_teacher.get(slot.id, (True, 5))
            if not is_avail:
                forbidden_teacher_slots += 1
                for r in range(num_rooms):
                    model.Add(x[(d_idx, s_idx, r)] == 0)

    # Hard 6: Room capacity — forbid (demand, *, room) where room.capacity
    # is below the classroom's cohort size.
    capacity_forbidden = 0
    for d_idx, (classroom, _, _) in enumerate(demands):
        needed = classroom_sizes.get(classroom.id, default_cohort_size)
        for r_idx, room in enumerate(rooms):
            if (room.capacity or 0) < needed:
                capacity_forbidden += 1
                for s in range(num_slots):
                    model.Add(x[(d_idx, s, r_idx)] == 0)

    # Soft objective: maximise sum of teacher preference_levels across picked
    # (demand, slot) pairs. Slots a teacher hasn't expressed an opinion on
    # default to 5 (the model's neutral mid-point).
    preference_terms = []
    for d_idx, (_, _, teacher) in enumerate(demands):
        avail_for_teacher = teacher_avail.get(teacher.id, {})
        for s_idx, slot in enumerate(time_slots):
            _is_avail, pref = avail_for_teacher.get(slot.id, (True, 5))
            for r in range(num_rooms):
                preference_terms.append(pref * x[(d_idx, s_idx, r)])
    if preference_terms:
        model.Maximize(sum(preference_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    logger.info(
        "cp_sat_solver_run status=%s demands=%d slots=%d rooms=%d "
        "teacher_unavailable_cells=%d room_capacity_forbidden_cells=%d "
        "objective=%s wall_seconds=%.3f",
        status,
        num_demands,
        num_slots,
        num_rooms,
        forbidden_teacher_slots,
        capacity_forbidden,
        solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        solver.WallTime(),
    )

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    schedule = Schedule.objects.create(
        name=f"{term.name} Schedule (OR-tools)",
        academic_year=academic_year,
        term=term,
        status="DRAFT",
        created_by=created_by,
    )
    for d in range(num_demands):
        classroom, subject, teacher = demands[d]
        for s in range(num_slots):
            for r in range(num_rooms):
                if solver.Value(x[(d, s, r)]) == 1:
                    ScheduleEntry.objects.create(
                        schedule=schedule,
                        classroom=classroom,
                        subject=subject,
                        teacher=teacher,
                        room=rooms[r],
                        time_slot=time_slots[s],
                    )
                    break
            else:
                continue
            break
    return schedule
