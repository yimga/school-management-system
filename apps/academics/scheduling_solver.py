"""
Phase 9: OR-tools timetabling solver.
Uses Google OR-Tools CP-SAT when available for constraint-based timetable generation;
otherwise falls back to TimetableGenerator.
"""

from __future__ import annotations

import importlib.util
from typing import Optional

from .scheduling import TimetableGenerator, Schedule


def _ortools_available() -> bool:
    """Return True if ortools.sat.python.cp_model is importable."""
    return importlib.util.find_spec("ortools.sat.python.cp_model") is not None


def generate_timetable_with_solver(
    academic_year,
    term,
    created_by,
    use_ortools: bool = True,
) -> Schedule:
    """
    Generate a timetable. If use_ortools=True and ortools is installed, use CP-SAT solver;
    else use TimetableGenerator (constraint satisfaction).
    """
    try:
        if use_ortools and _ortools_available():
            # Build a minimal CP-SAT model: assign (classroom, subject) to (room, slot) with no conflicts.
            schedule = _solve_with_ortools(academic_year, term, created_by)
            if schedule is not None:
                return schedule
    except ImportError:
        pass
    gen = TimetableGenerator(academic_year=academic_year, term=term)
    return gen.generate_schedule(created_by=created_by)


def _solve_with_ortools(academic_year, term, created_by) -> Optional[Schedule]:
    """Use OR-Tools CP-SAT to assign classes to (room, time_slot). Returns Schedule or None."""
    from apps.academics.models import SubjectAssignment
    from apps.evals.models import TeacherAssignment
    from .scheduling import Schedule, ScheduleEntry, Room, TimeSlot

    time_slots = list(
        TimeSlot.objects.filter(is_active=True).order_by("day_of_week", "start_time")
    )
    rooms = list(Room.objects.filter(is_available=True).order_by("capacity"))

    if not time_slots or not rooms:
        return None

    # Build list of (classroom, subject, teacher_user) from SubjectAssignment + TeacherAssignment
    demands = []
    subject_assignments = SubjectAssignment.objects.filter(
        academic_year=academic_year,
        term=term,
    ).select_related("classroom", "subject")
    for sa in subject_assignments:
        ta = (
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

    model = __import__(
        "ortools.sat.python.cp_model", fromlist=["cp_model"]
    ).cp_model.CpModel()
    num_demands = len(demands)
    num_slots = len(time_slots)
    num_rooms = len(rooms)

    # x[d, s, r] = 1 if demand d is in slot s and room r
    x = {}
    for d in range(num_demands):
        for s in range(num_slots):
            for r in range(num_rooms):
                x[(d, s, r)] = model.NewBoolVar(f"x_{d}_{s}_{r}")

    # Each demand assigned exactly once
    for d in range(num_demands):
        model.Add(
            sum(x[(d, s, r)] for s in range(num_slots) for r in range(num_rooms)) == 1
        )

    # Each (slot, room) at most one demand
    for s in range(num_slots):
        for r in range(num_rooms):
            model.Add(sum(x[(d, s, r)] for d in range(num_demands)) <= 1)

    # Teacher conflict: same teacher not in two places in same slot
    for s in range(num_slots):
        for d1 in range(num_demands):
            for d2 in range(d1 + 1, num_demands):
                if demands[d1][2].id == demands[d2][2].id:
                    model.Add(
                        sum(x[(d1, s, r)] for r in range(num_rooms))
                        + sum(x[(d2, s, r)] for r in range(num_rooms))
                        <= 1
                    )

    solver = __import__(
        "ortools.sat.python.cp_model", fromlist=["cp_model"]
    ).cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    if status not in (1, 4):  # OPTIMAL or FEASIBLE
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
