"""In-product timetable flow: generate -> review clashes -> publish (Stack A).

This is the ONE real, persisting timetable surface. It drives the wired CSP
generator ``apps.academics.scheduling.TimetableGenerator.generate_schedule``
(which writes ``Schedule`` + ``ScheduleEntry``), renders the persisted draft as a
days x periods grid with a clash panel from ``evaluate_schedule`` /
``detect_conflicts``, and REFUSES to publish while any hard violation remains.

Gating on every write view is ``@login_required`` -> ``@require_school`` ->
``@require_permission`` (innermost); every query is scoped to ``request.school``
through the ``academic_year__school`` graph (``Schedule`` has no direct school FK).
"""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST, require_http_methods

from apps.accounts.decorators import login_required, require_permission
from apps.academics.scheduling import (
    Schedule,
    ScheduleEntry,
    TimeSlot,
    TimetableGenerator,
    find_schedule_booking_conflicts,
)
from apps.academics.scheduling_evaluation import evaluate_schedule
from apps.academics.services import get_active_year_and_term
from apps.schools.mixins import require_school

# Timetabling is academic scheduling — gate it on the academics-management code
# (seeded to HOD / DEAN / registrar / admin tier). ``require_permission`` also
# admits the tenant-admin tier additively, so converting to this gate can only
# preserve-or-widen who can build the master timetable.
_TIMETABLE_PERMISSION = "grades.manage"

_DAY_LABELS = dict(TimeSlot.DAYS_OF_WEEK)


def _build_grid(entries: list) -> dict:
    """Shape schedule entries into a days x periods grid for the template.

    Rows are time-of-day period bands (keyed by start/end time); columns are the
    days present in the schedule. Each cell holds the entries booked in that
    (day, band) — a master schedule can have one per cohort, so cells are lists.
    """
    days = sorted({e.time_slot.day_of_week for e in entries})
    band_keys = sorted({(e.time_slot.start_time, e.time_slot.end_time) for e in entries})

    band_label: dict = {}
    for e in entries:
        key = (e.time_slot.start_time, e.time_slot.end_time)
        band_label.setdefault(
            key,
            e.time_slot.slot_name
            or f"{e.time_slot.start_time:%H:%M}–{e.time_slot.end_time:%H:%M}",
        )

    rows = []
    for start, end in band_keys:
        cells = []
        for day in days:
            cells.append(
                [
                    e
                    for e in entries
                    if e.time_slot.day_of_week == day
                    and e.time_slot.start_time == start
                    and e.time_slot.end_time == end
                ]
            )
        rows.append({"label": band_label[(start, end)], "cells": cells})

    return {
        "day_headers": [_DAY_LABELS.get(d, str(d)) for d in days],
        "rows": rows,
        "has_entries": bool(entries),
    }


def _dedupe_conflicts(raw_conflicts: list) -> list:
    seen = set()
    unique = []
    for c in raw_conflicts:
        key = (c["type"], tuple(sorted(c.get("entries", []))))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


@login_required
@require_school
@require_http_methods(["GET", "POST"])
@require_permission(_TIMETABLE_PERMISSION)
def timetable_generate(request):
    """GET opens the workspace; POST persists a fresh DRAFT then reviews it."""
    if request.method == "GET":
        return redirect("accounts:ops_timetabling")
    school = request.school
    year, term = get_active_year_and_term(school=school)
    if not (year and term):
        messages.error(
            request,
            _("Set an active academic year and term before building a timetable."),
        )
        return redirect("accounts:ops_timetabling")

    # Mint a new DRAFT beside any live PUBLISHED plan. Per-plan uniqueness
    # (migration 0066) lets drafts coexist with published; replace-on-live
    # happens at publish via Schedule.publish() demotion — not here.
    # Stale drafts for this term are cleared so regenerate stays idempotent
    # without destroying the timetable families currently depend on.
    # tenant-isolation-allow: scoped-via-academic-year-school-fk-graph
    Schedule.objects.filter(
        academic_year=year,
        term=term,
        academic_year__school=school,
        status="DRAFT",
    ).delete()

    generator = TimetableGenerator(year, term)
    schedule = generator.generate_schedule(created_by=request.user)

    placed = evaluate_schedule(schedule)["entry_count"]
    if placed == 0:
        messages.warning(
            request,
            _(
                "No classes could be placed. Add subject assignments (class + "
                "subject + teacher), rooms, and active time slots, then try again."
            ),
        )
    else:
        messages.success(
            request,
            _(
                "Draft timetable generated with %(n)d placed classes. "
                "Review clashes below before publishing."
            )
            % {"n": placed},
        )
    return redirect("academics:timetable_review", schedule_id=schedule.id)


@login_required
@require_school
@require_permission(_TIMETABLE_PERMISSION)
def timetable_review(request, schedule_id):
    """GET: render the persisted schedule as a grid + a clash panel."""
    school = request.school
    # tenant-isolation-allow: scoped-via-academic-year-school-fk-graph
    schedule = get_object_or_404(
        Schedule.objects.select_related("academic_year", "term"),
        pk=schedule_id,
        academic_year__school=school,
    )
    entries = list(
        # tenant-isolation-allow: scoped-via-parent-schedule-which-is-school-scoped
        ScheduleEntry.objects.filter(schedule=schedule, is_cancelled=False)
        .select_related("classroom", "subject", "teacher", "room", "time_slot")
        .order_by("time_slot__day_of_week", "time_slot__start_time")
    )

    evaluation = evaluate_schedule(schedule)
    hard_total = evaluation["hard_violations_total"]

    generator = TimetableGenerator(schedule.academic_year, schedule.term)
    conflicts = _dedupe_conflicts(generator.detect_conflicts(schedule))

    # Metric-15 (part B): scheduled-class vs ad-hoc room booking (#10) cross-check.
    booking_conflicts = find_schedule_booking_conflicts(schedule)

    return render(
        request,
        "academics/timetable_review.html",
        {
            "schedule": schedule,
            "grid": _build_grid(entries),
            "entries": entries,
            "evaluation": evaluation,
            "conflicts": conflicts,
            "booking_conflicts": booking_conflicts,
            "hard_violations_total": hard_total,
            "is_published": schedule.status == "PUBLISHED",
            "can_publish": (
                hard_total == 0
                and not booking_conflicts
                and schedule.status != "PUBLISHED"
            ),
        },
    )


@login_required
@require_school
@require_POST
@require_permission(_TIMETABLE_PERMISSION)
def timetable_publish(request, schedule_id):
    """POST: publish the schedule, but REFUSE while any hard violation remains."""
    school = request.school
    # tenant-isolation-allow: scoped-via-academic-year-school-fk-graph
    schedule = get_object_or_404(
        Schedule.objects.select_related("academic_year", "term"),
        pk=schedule_id,
        academic_year__school=school,
    )

    hard_total = evaluate_schedule(schedule)["hard_violations_total"]
    if hard_total > 0:
        messages.error(
            request,
            _(
                "Cannot publish: %(n)d unresolved clash(es). Resolve the conflicts "
                "and regenerate before publishing."
            )
            % {"n": hard_total},
        )
        return redirect("academics:timetable_review", schedule_id=schedule.id)

    # Metric-15 (part B): refuse if any scheduled class collides with a confirmed
    # ad-hoc booking of the linked room's resource (#10). Schedule stays DRAFT.
    booking_conflicts = find_schedule_booking_conflicts(schedule)
    if booking_conflicts:
        first = booking_conflicts[0]
        messages.error(
            request,
            _(
                "Cannot publish: room %(room)s is already booked (%(title)s) at "
                "%(when)s. Cancel or move the booking, then publish."
            )
            % {
                "room": first["room"],
                "title": first["booking_title"],
                "when": timezone.localtime(first["occurrence_start"]).strftime(
                    "%Y-%m-%d %H:%M"
                )
                if timezone.is_aware(first["occurrence_start"])
                else first["occurrence_start"].strftime("%Y-%m-%d %H:%M"),
            },
        )
        return redirect("academics:timetable_review", schedule_id=schedule.id)

    schedule.publish()
    messages.success(
        request, _("Timetable published. Teachers now see it in their portal.")
    )
    return redirect("academics:timetable_review", schedule_id=schedule.id)


@login_required
@require_school
@require_POST
@require_permission(_TIMETABLE_PERMISSION)
def timetable_cancel_entry(request, schedule_id, entry_id):
    """POST: cancel a draft placement so operators can clear hard clashes."""
    school = request.school
    # tenant-isolation-allow: scoped-via-academic-year-school-fk-graph
    schedule = get_object_or_404(
        Schedule.objects.select_related("academic_year", "term"),
        pk=schedule_id,
        academic_year__school=school,
    )
    if schedule.status == "PUBLISHED":
        messages.error(request, _("Published timetables cannot cancel placements here."))
        return redirect("academics:timetable_review", schedule_id=schedule.id)

    # tenant-isolation-allow: scoped-via-parent-schedule-which-is-school-scoped
    entry = get_object_or_404(
        ScheduleEntry.objects.filter(schedule=schedule),
        pk=entry_id,
    )
    if entry.is_cancelled:
        messages.info(request, _("That placement is already cancelled."))
    else:
        entry.is_cancelled = True
        entry.save(update_fields=["is_cancelled"])
        messages.success(request, _("Placement removed from the draft."))
    return redirect("academics:timetable_review", schedule_id=schedule.id)
