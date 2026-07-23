"""Enrollment lifecycle — the one place a student's placement may change.

Item 2.2 of ``docs/PLATFORM_GLOBALIZATION_PROGRAM.md``.

Before this module, year-end promotion was a destructive ``UPDATE`` on
``StudentProfile.classroom``/``.academic_year`` (see the pre-change bodies of
``apps/academics/management/commands/run_auto_promotion.py`` and
``apps/accounts/tasks.py::_apply_rollover_proposal_impl``). Last year's placement
was overwritten, so there was no academic history, *repeating a year could not be
expressed at all*, and ``PromotionRule`` was never consulted by the promotion job
— a failing student advanced exactly like a passing one.

Every function here OPENS a new :class:`~apps.people.models.Enrollment` and CLOSES
the prior one. Nothing is overwritten. The legacy student-row fields are kept in
step as a projection so existing readers are untouched.

COUNTRY NEUTRALITY. ``PromotionRule`` still carries a Cameroonian ITC/ATC option,
which is out of scope here; what this module fixes is that the *decision* is now
a data-driven three-band model — retain / conditionally promote / promote — which
every school system expresses, rather than a single pass line applied to nobody.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.people.models import Enrollment, StudentProfile


#: What to do with a student the rules cannot decide on — either no
#: ``PromotionRule`` exists for their scope, or no marks were recorded.
#:
#: ``promote`` is the DEFAULT ON PURPOSE: it reproduces the pre-2.2 behaviour
#: exactly for every tenant that has not configured promotion rules, so turning
#: this on cannot re-class anybody. Schools that do configure rules get them
#: honoured, which is the actual defect being fixed.
NO_DATA_PROMOTE = "promote"
NO_DATA_RETAIN = "retain"
NO_DATA_SKIP = "skip"
NO_DATA_POLICIES = (NO_DATA_PROMOTE, NO_DATA_RETAIN, NO_DATA_SKIP)

#: Legacy status strings returned by ``apps.reports.services.get_promotion_status``.
#: Kept as-is because report cards and two templates render them verbatim.
STATUS_PROMOTED = "PROMOTED"
STATUS_REPEAT = "REPEAT"
STATUS_DEMOTED = "DEMOTED"
STATUS_PENDING = "PENDING"
STATUS_NO_DATA = "NO_DATA"


@dataclass
class PromotionDecision:
    """What the rules say should happen to one student at year end."""

    outcome: str
    #: Legacy ``get_promotion_status`` string, preserved for report cards.
    status_code: str
    average: Optional[float] = None
    #: True when the student moves to the next grade.
    advances: bool = False
    #: True when no rule and/or no marks existed and a policy decided instead.
    undecided: bool = False
    reason: str = ""
    rule: object = None

    @property
    def retains(self) -> bool:
        return self.outcome == Enrollment.Outcome.RETAINED


@dataclass
class PromotionRunResult:
    """Per-cohort summary. Counts are disjoint; they sum to the cohort size."""

    # No ``graduated`` counter: this cohort runner promotes or retains, it never
    # graduates. Graduation is an explicit per-student decision on the rollover
    # proposal (``RolloverProposalItem.is_graduate``), so a counter here could
    # only ever report zero — and a number that cannot move is worse than none.
    promoted: int = 0
    conditionally_promoted: int = 0
    retained: int = 0
    skipped: int = 0
    skipped_reasons: dict = field(default_factory=dict)

    def note_skip(self, reason: str) -> None:
        self.skipped += 1
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1

    def as_dict(self) -> dict:
        return {
            "promoted": self.promoted,
            "conditionally_promoted": self.conditionally_promoted,
            "retained": self.retained,
            "skipped": self.skipped,
            "skipped_reasons": dict(self.skipped_reasons),
        }


# --------------------------------------------------------------------------
# Enrollment lifecycle primitives
# --------------------------------------------------------------------------


def open_enrollment(
    student: StudentProfile,
    academic_year,
    classroom=None,
    *,
    specialty=None,
    section: str = "",
    entry_date=None,
    previous_enrollment: Optional[Enrollment] = None,
    close_existing: bool = True,
    close_outcome: str = Enrollment.Outcome.PROMOTED,
) -> Enrollment:
    """Open a NEW enrollment, closing whatever was open before it.

    The DB constraint ``people_enrollment_one_active_per_student`` guarantees at
    most one open row, which is what makes "current class" a derivation rather
    than a guess. Passing ``close_existing=False`` when one is already open is
    therefore an IntegrityError, deliberately.
    """
    with transaction.atomic():
        current = student.current_enrollment
        if current is not None and close_existing:
            if current.academic_year_id == getattr(
                academic_year, "pk", academic_year
            ) and current.classroom_id == getattr(classroom, "pk", classroom):
                # Same placement — idempotent, do not churn history. Still
                # re-project onto the student row: a caller may be healing a
                # row that drifted away from its enrollment.
                current.sync_student_row()
                return current
            current.close(close_outcome, exit_date=entry_date)
            if previous_enrollment is None:
                previous_enrollment = current
        return Enrollment.objects.create(
            school_id=student.school_id,
            student=student,
            academic_year=academic_year,
            classroom=classroom,
            specialty=specialty if specialty is not None else student.specialty,
            section=section or (student.section or ""),
            status=Enrollment.Status.ACTIVE,
            entry_date=entry_date or timezone.now().date(),
            previous_enrollment=previous_enrollment,
        )


def ensure_enrollment(
    student: StudentProfile, *, academic_year=None, classroom=None
) -> Optional[Enrollment]:
    """Idempotently guarantee an open enrollment matching the student row.

    Used by paths that still write the legacy fields (imports, admissions,
    provisioning) so they gain history without being rewritten. Returns None
    when there is nothing to anchor on — a student with no academic year.
    """
    year = academic_year or student.academic_year
    if year is None:
        return None
    room = classroom if classroom is not None else student.classroom
    current = student.current_enrollment
    if current is not None:
        if current.academic_year_id == year.pk and current.classroom_id == (
            room.pk if room is not None else None
        ):
            return current
        return open_enrollment(student, year, room)
    return Enrollment.objects.create(
        school_id=student.school_id,
        student=student,
        academic_year=year,
        classroom=room,
        specialty=student.specialty,
        section=student.section or "",
        status=Enrollment.Status.ACTIVE,
        entry_date=student.joined_date or timezone.now().date(),
    )


def set_placement(
    student: StudentProfile,
    *,
    classroom=None,
    academic_year=None,
    entry_date=None,
) -> Optional[Enrollment]:
    """Reflect a placement change made on the student row onto the enrollment.

    Called by the paths that legitimately still write the legacy fields — the
    OneRoster rails and the admin bulk-assign action. Without it those writers
    would leave the student row and the enrollment disagreeing, and the whole
    point of the enrollment is that it is the one that is right.

    * SAME academic year -> amend the open enrollment in place. A mid-year class
      move is not a new year and must not manufacture a second history row.
    * DIFFERENT academic year -> open a new enrollment, closing the prior one.
    """
    year = academic_year if academic_year is not None else student.academic_year
    if year is None:
        return None
    year_pk = getattr(year, "pk", year)
    room = classroom if classroom is not None else student.classroom
    room_pk = getattr(room, "pk", room)

    current = student.current_enrollment
    if current is None:
        return ensure_enrollment(student, academic_year=year, classroom=room)
    if current.academic_year_id != year_pk:
        return open_enrollment(student, year, room, entry_date=entry_date)
    if current.classroom_id != room_pk:
        current.classroom_id = room_pk
        current.save(update_fields=["classroom", "updated_at"])
    return current


def graduate_student(
    student: StudentProfile, target_year, *, exit_date=None
) -> Optional[Enrollment]:
    """Close the open enrollment as GRADUATED. Opens nothing — they have left."""
    current = student.current_enrollment
    if current is not None:
        current.close(
            Enrollment.Outcome.GRADUATED,
            exit_date=exit_date,
            status=Enrollment.Status.COMPLETED,
        )
    return current


# --------------------------------------------------------------------------
# Rule resolution
# --------------------------------------------------------------------------


def annual_average_for(student: StudentProfile, academic_year) -> Optional[float]:
    """The student's annual average, or None when nothing was recorded."""
    # Lazy: apps.reports imports apps.people, so a module-level import cycles.
    from apps.academics.models import Term
    from apps.reports.services import _annual_average_for_student

    terms = list(
        # tenant-isolation-allow: term-lookup-bounded-by-tenant-scoped-academic-year-fk
        Term.objects.filter(academic_year=academic_year).order_by(
            "position", "start_date"
        )
    )
    if not terms:
        return None
    return _annual_average_for_student(student, terms)


def resolve_promotion_decision(
    student: StudentProfile,
    academic_year,
    average: Optional[float] = None,
    *,
    no_data_policy: str = NO_DATA_PROMOTE,
) -> PromotionDecision:
    """Turn ``PromotionRule`` + the student's average into a real decision.

    This is the fix for "the promotion job ignores PromotionRule". The three
    bands, from the top:

    * ``average >= promotion_average``            -> PROMOTED
    * ``>= conditional_promotion_average``        -> CONDITIONALLY_PROMOTED
    * anything lower                              -> RETAINED

    A ``DEMOTED`` verdict from the legacy status function (average below the
    school's floor) also lands on RETAINED: this codebase has no "move down a
    grade" target to promote into, so retention is the only honest expression of
    it. The original verdict is preserved in ``reason`` rather than discarded.
    """
    from apps.reports.services import (
        _promotion_rule_for_student,
        get_promotion_status,
    )

    if average is None:
        average = annual_average_for(student, academic_year)

    status_code = get_promotion_status(student, academic_year, average)

    if status_code in (STATUS_NO_DATA, STATUS_PENDING):
        reason = (
            "No marks recorded for the year"
            if status_code == STATUS_NO_DATA
            else "No PromotionRule configured for this scope"
        )
        if no_data_policy == NO_DATA_RETAIN:
            return PromotionDecision(
                outcome=Enrollment.Outcome.RETAINED,
                status_code=status_code,
                average=average,
                advances=False,
                undecided=True,
                reason=reason,
            )
        if no_data_policy == NO_DATA_SKIP:
            return PromotionDecision(
                outcome="",
                status_code=status_code,
                average=average,
                advances=False,
                undecided=True,
                reason=reason,
            )
        return PromotionDecision(
            outcome=Enrollment.Outcome.PROMOTED,
            status_code=status_code,
            average=average,
            advances=True,
            undecided=True,
            reason=reason,
        )

    rule = _promotion_rule_for_student(student, academic_year)

    if status_code == STATUS_PROMOTED:
        return PromotionDecision(
            outcome=Enrollment.Outcome.PROMOTED,
            status_code=status_code,
            average=average,
            advances=True,
            rule=rule,
        )

    conditional = getattr(rule, "conditional_promotion_average", None)
    if (
        conditional is not None
        and average is not None
        and float(average) >= float(conditional)
    ):
        return PromotionDecision(
            outcome=Enrollment.Outcome.CONDITIONALLY_PROMOTED,
            status_code=status_code,
            average=average,
            advances=True,
            reason=(
                f"Average {float(average):.2f} is within the conditional band "
                f"({float(conditional):.2f}-{float(rule.promotion_average):.2f})"
            ),
            rule=rule,
        )

    return PromotionDecision(
        outcome=Enrollment.Outcome.RETAINED,
        status_code=status_code,
        average=average,
        advances=False,
        reason=(
            "Below the school's floor average"
            if status_code == STATUS_DEMOTED
            else "Below the promotion average"
        ),
        rule=rule,
    )


def outcome_for_manual_placement(
    source_classroom, target_classroom, status_code: str = ""
) -> str:
    """Outcome for a placement a HUMAN chose (the rollover review screen).

    The operator picks the next class; this records what that choice *means* so
    the history is truthful rather than uniformly "PROMOTED":

    * same grade next year                          -> RETAINED
    * a different grade despite a failing verdict    -> CONDITIONALLY_PROMOTED
    * otherwise                                      -> PROMOTED
    """
    if (
        source_classroom is not None
        and target_classroom is not None
        and source_classroom.name == target_classroom.name
    ):
        return Enrollment.Outcome.RETAINED
    if status_code in (STATUS_REPEAT, STATUS_DEMOTED):
        return Enrollment.Outcome.CONDITIONALLY_PROMOTED
    return Enrollment.Outcome.PROMOTED


def resolve_target_classroom(
    decision: PromotionDecision,
    source_classroom,
    target_year,
    mappings: dict,
):
    """Which class the student lands in next year.

    Advancing -> the configured ``ClassroomPromotionMapping`` target.
    Retained  -> the SAME grade in the target year, matched by classroom name.

    Retention is exactly the case that was inexpressible before: the student
    needs a *different year's* row for the *same* grade, which a single field on
    the student row cannot hold.
    """
    from apps.academics.models import Classroom

    if source_classroom is None:
        return None
    if decision.advances:
        mapping = mappings.get(source_classroom.pk)
        return getattr(mapping, "target_classroom", None) if mapping else None
    # tenant-isolation-allow: classroom-match-bounded-by-tenant-academic-year-then-conditional-school-id
    same_grade = Classroom.objects.filter(
        academic_year=target_year, name=source_classroom.name
    )
    if source_classroom.school_id:
        same_grade = same_grade.filter(school_id=source_classroom.school_id)
    return same_grade.first()


# --------------------------------------------------------------------------
# Cohort promotion
# --------------------------------------------------------------------------


def promote_student(
    student: StudentProfile,
    source_year,
    target_year,
    mappings: dict,
    *,
    decision: Optional[PromotionDecision] = None,
    no_data_policy: str = NO_DATA_PROMOTE,
    dry_run: bool = False,
) -> tuple[Optional[Enrollment], PromotionDecision, str]:
    """Promote (or retain) ONE student. Returns (enrollment, decision, skip_reason).

    ``enrollment`` is the NEW open enrollment; the prior one is closed with the
    decision's outcome and stays queryable forever.
    """
    if decision is None:
        decision = resolve_promotion_decision(
            student, source_year, no_data_policy=no_data_policy
        )
    if not decision.outcome:
        return None, decision, "undecided"

    source_enrollment = student.enrollment_for_year(source_year)
    source_classroom = (
        source_enrollment.classroom
        if source_enrollment is not None and source_enrollment.classroom_id
        else student.classroom
    )
    target_classroom = resolve_target_classroom(
        decision, source_classroom, target_year, mappings
    )
    if target_classroom is None:
        return (
            None,
            decision,
            "no_target_classroom" if decision.advances else "no_repeat_classroom",
        )
    if dry_run:
        return None, decision, ""

    with transaction.atomic():
        previous = source_enrollment
        # Close whatever is open before opening the next one — the DB constraint
        # allows exactly one active row, and closing is how history is created.
        # Iterating rather than closing `source_enrollment` directly also covers
        # the drifted case where the student row says one year and the open
        # enrollment says another.
        for open_row in student.enrollments.filter(status=Enrollment.Status.ACTIVE):
            open_row.close(
                decision.outcome,
                reason=decision.reason,
                decision_average=decision.average,
            )
            if previous is None:
                previous = open_row
        new_enrollment = Enrollment.objects.create(
            school_id=student.school_id,
            student=student,
            academic_year=target_year,
            classroom=target_classroom,
            specialty=student.specialty,
            section=student.section or "",
            status=Enrollment.Status.ACTIVE,
            entry_date=getattr(target_year, "start_date", None)
            or timezone.now().date(),
            previous_enrollment=previous,
        )
    return new_enrollment, decision, ""


def promote_cohort(
    source_year,
    target_year,
    *,
    school_id=None,
    mappings: Optional[dict] = None,
    no_data_policy: str = NO_DATA_PROMOTE,
    dry_run: bool = False,
    on_student=None,
) -> PromotionRunResult:
    """Promote everyone enrolled in ``source_year``, honouring PromotionRule."""
    from apps.academics.models import ClassroomPromotionMapping

    if no_data_policy not in NO_DATA_POLICIES:
        raise ValueError(
            f"no_data_policy must be one of {NO_DATA_POLICIES}, got {no_data_policy!r}"
        )
    if mappings is None:
        # tenant-isolation-allow: promotion-mapping-bounded-by-tenant-source-and-target-year-then-conditional-school-id
        mapping_qs = ClassroomPromotionMapping.objects.filter(
            source_year=source_year, target_year=target_year
        ).select_related("source_classroom", "target_classroom")
        if school_id:
            mapping_qs = mapping_qs.filter(school_id=school_id)
        mappings = {m.source_classroom_id: m for m in mapping_qs}

    # tenant-isolation-allow: active-students-bounded-by-tenant-source-year-then-conditional-school-id
    students = StudentProfile.objects.filter(
        academic_year=source_year, is_active=True
    ).select_related("classroom", "specialty")
    if school_id:
        students = students.filter(school_id=school_id)

    result = PromotionRunResult()
    for student in students:
        enrollment, decision, skip_reason = promote_student(
            student,
            source_year,
            target_year,
            mappings,
            no_data_policy=no_data_policy,
            dry_run=dry_run,
        )
        if skip_reason:
            result.note_skip(skip_reason)
        elif decision.outcome == Enrollment.Outcome.CONDITIONALLY_PROMOTED:
            result.conditionally_promoted += 1
        elif decision.outcome == Enrollment.Outcome.RETAINED:
            result.retained += 1
        else:
            result.promoted += 1
        if on_student is not None:
            on_student(student, decision, enrollment, skip_reason)
    return result
