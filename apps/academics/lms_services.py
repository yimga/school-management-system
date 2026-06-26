"""Canonical LMS assignment-submission service layer — the homework loop.

This is the single write path that BOTH the online portal views and the offline
SODP applier (``platform_runtime.offline_queue._apply_lms_submission``) call, so an
online submit and an offline-then-synced submit converge on ONE store:
``academics.LMSSubmission`` — the canonical assignment/submission pair documented in
``models_lms.py`` ("the minimal canonical pair other apps can wire to").

The ``lesson_homework_kernel`` ``School.settings``-JSON Homework store is the legacy /
offline-edge representation; THIS module is the system of record. Keeping one write
path here is what lets the offline rail stay canonical-correct instead of forking a
second submission store.

Design contract:
- Tenant-scoped: school is always resolved from the assignment (never trusted from input).
- Idempotent / remote-wins: a replayed offline action for an already-submitted piece of
  work never double-writes or clobbers a graded submission (mirrors the dedup semantics
  the existing offline appliers use).
- Pure of request/HTTP concerns: callers pass resolved model instances.
"""

from __future__ import annotations

import logging
from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.academics.models_lms import LMSAssignment, LMSSubmission

logger = logging.getLogger(__name__)

# ── Gradebook materialization (homework grade -> evals.Evaluation) ─────────────
# The Evaluation component a graded homework score flows into. Writing into the
# authoritative gradebook is DESTRUCTIVE (it would overwrite a teacher's manually
# entered marks in that slot), so this is OPT-IN per school: it stays "none" until
# a school points School.settings['lms_homework_eval_component'] at a dedicated
# component. The chosen slot is then HOMEWORK-OWNED. Maps config value -> (the
# Evaluation field, the AssessmentWeights attr that gates it).
_HOMEWORK_EVAL_COMPONENTS = {
    "seq1": ("seq1_score", "seq1_weight"),
    "seq2": ("seq2_score", "seq2_weight"),
    "practical": ("practical_score", "practical_weight"),
}
_HOMEWORK_EVAL_DISABLED = "none"


# Submission states that mean "the student has already turned this in" — a replayed
# offline submit for one of these is a no-op (remote-wins) unless force=True.
_TERMINAL_SUBMITTED_STATES = frozenset(
    {
        LMSSubmission.Status.SUBMITTED,
        LMSSubmission.Status.LATE,
        LMSSubmission.Status.GRADED,
        LMSSubmission.Status.RETURNED,
        LMSSubmission.Status.EXCUSED,
    }
)

_MAX_CONTENT_CHARS = 8000


class AssignmentClosedError(ValueError):
    """Raised when a student tries to submit to an assignment not open for submissions."""


@transaction.atomic
def submit_assignment(
    *,
    assignment: LMSAssignment,
    student,
    content: str = "",
    attachment=None,
    today: date_type | None = None,
    force: bool = False,
) -> tuple[LMSSubmission, bool]:
    """Record (or update) ``student``'s submission for ``assignment``.

    Returns ``(submission, changed)`` where ``changed`` is ``False`` when an existing
    already-submitted row was left untouched (remote-wins dedup) — the signal an offline
    replay uses to report a clean no-op rather than a double-submit.

    Raises ``AssignmentClosedError`` when the assignment is not open for submissions and
    no prior submission exists (an offline action queued while the assignment was open
    but synced after it closed still lands, via ``force``-less re-entry on the existing row).
    """
    school = assignment.school

    # (assignment, student) is unique_together; school is carried for tenant-scope clarity.
    submission, created = LMSSubmission.objects.get_or_create(
        assignment=assignment,
        student=student,
        school=school,
        defaults={"status": LMSSubmission.Status.NOT_SUBMITTED},
    )

    # Remote-wins: an already-turned-in (esp. graded) submission is authoritative.
    if (
        not created
        and not force
        and submission.status in _TERMINAL_SUBMITTED_STATES
    ):
        return submission, False

    if not assignment.is_open_for_submissions and created:
        # No prior work AND the window is closed → reject (and roll back the empty row).
        raise AssignmentClosedError("assignment_not_open_for_submissions")

    submission.content = (content or "")[:_MAX_CONTENT_CHARS]
    if attachment is not None:
        submission.attachment = attachment

    # mark_submitted() stamps submitted_at and resolves SUBMITTED vs LATE from due_at.
    submission.mark_submitted()
    if today is not None and assignment.due_at:
        # Allow callers (offline replay) to pin "late" to the original offline timestamp.
        due_local_date = timezone.localtime(assignment.due_at).date()
        if today > due_local_date:
            submission.status = LMSSubmission.Status.LATE

    submission.save()
    return submission, True


@transaction.atomic
def grade_submission(
    *,
    submission: LMSSubmission,
    score,
    feedback: str = "",
    graded_by=None,
) -> LMSSubmission:
    """Grade a submission (teacher action). Sets score/feedback and stamps the grade.

    Evaluation materialization into ``evals.Evaluation`` is wired by the teacher grading
    surface (it needs the resolved AssessmentWeights / term context); this function owns
    only the LMS-side grade state so the student loop and the offline replay path share it.
    """
    submission.score = score
    submission.feedback = (feedback or "")[:8000]
    submission.graded_at = timezone.now()
    submission.graded_by = graded_by
    submission.status = LMSSubmission.Status.GRADED
    submission.save(
        update_fields=["score", "feedback", "graded_at", "graded_by", "status", "updated_at"]
    )
    # Mirror the grade into the gradebook when the school opted in. Best-effort:
    # a materialization failure must NEVER break grading (the LMS grade is the
    # source of truth; the Evaluation is a derived convenience).
    try:
        materialize_evaluation_from_submission(submission=submission)
    except Exception as exc:  # noqa: BLE001 — gradebook sync is derived, never load-bearing
        logger.warning(
            "lms grade->evaluation materialization skipped sub=%s err=%s",
            getattr(submission, "pk", None),
            exc,
        )
    return submission


def _resolve_homework_eval_component(school) -> str:
    """The Evaluation component homework grades flow into for ``school``.

    School-configurable via ``School.settings['lms_homework_eval_component']``
    (``seq1`` | ``seq2`` | ``practical`` | ``none``). Defaults to ``none`` —
    materialization is off until a school explicitly picks a homework-owned slot,
    so it can never silently overwrite manually entered marks.
    """
    raw = ""
    try:
        cfg = getattr(school, "settings", None)
        if isinstance(cfg, dict):
            raw = str(cfg.get("lms_homework_eval_component") or "").strip().lower()
    except Exception:  # noqa: BLE001 — config read is best-effort
        raw = ""
    return raw if raw in _HOMEWORK_EVAL_COMPONENTS else _HOMEWORK_EVAL_DISABLED


def _convert_homework_score(raw_score, points_possible, scale) -> Decimal:
    """Rescale a raw homework score onto the school's operational grade scale.

    A submission is scored on the assignment's ``points_possible`` axis (e.g. /100)
    but Evaluation components are validated against the school's grade scale (e.g.
    /20), so an unconverted score would be out of range or wildly wrong. Clamped to
    ``[0, scale]`` and rounded to 2dp. e.g. ``80/100`` on a /20 school -> ``16.00``.
    """
    try:
        raw = Decimal(str(raw_score))
        pts = Decimal(str(points_possible or 0))
        sc = Decimal(str(scale or 0))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal("0")
    if pts <= 0 or sc <= 0:
        return Decimal("0")
    value = (raw / pts) * sc
    if value < 0:
        value = Decimal("0")
    elif value > sc:
        value = sc
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def materialize_evaluation_from_submission(*, submission) -> dict:
    """Upsert a graded LMS homework submission into the gradebook (``evals.Evaluation``).

    Idempotent: keyed on ``(academic_year, term, subject_assignment, student)`` so a
    re-grade updates the SAME row instead of duplicating. Writes ONLY the school's
    configured homework component, rescaled onto the school's grade scale. Returns a
    structured ``{"materialized": bool, "reason"/"component"/...}`` and NEVER raises;
    it skips cleanly when the school disabled it, the slot carries zero weight, the
    assignment has no term, the student has no academic year, or no matching
    SubjectAssignment exists (homework on a subject that isn't a graded roster slot).
    """
    assignment = submission.assignment
    school = assignment.school
    student = submission.student

    if submission.score is None or submission.status != LMSSubmission.Status.GRADED:
        return {"materialized": False, "reason": "not_graded"}

    component = _resolve_homework_eval_component(school)
    if component == _HOMEWORK_EVAL_DISABLED:
        return {"materialized": False, "reason": "disabled"}
    field_name, weight_attr = _HOMEWORK_EVAL_COMPONENTS[component]

    term = assignment.term
    if term is None:
        return {"materialized": False, "reason": "no_term"}
    academic_year = getattr(student, "academic_year", None)
    if academic_year is None:
        return {"materialized": False, "reason": "no_student_year"}

    from apps.academics.models import SubjectAssignment
    from apps.evals.grading_provisioning import resolve_school_score_scale
    from apps.evals.models import AssessmentWeights, Evaluation

    # Resolve the gradebook SubjectAssignment from the STUDENT's roster dimensions
    # (so Evaluation.clean()'s year/class/specialty invariants hold) plus the
    # assignment's subject + term.
    sa = SubjectAssignment.objects.filter(
        school=school,
        academic_year=academic_year,
        term=term,
        classroom_id=getattr(student, "classroom_id", None),
        specialty_id=getattr(student, "specialty_id", None),
        subject_id=assignment.subject_id,
    ).first()
    if sa is None:
        return {"materialized": False, "reason": "no_subject_assignment"}

    # Never inject into an unweighted slot (e.g. a percentage/GPA school whose model
    # doesn't use seq1) — that would surprise the gradebook composite.
    weights = AssessmentWeights.get_for(
        academic_year, getattr(student, "classroom", None), term
    )
    if int(getattr(weights, weight_attr, 0) or 0) <= 0:
        return {"materialized": False, "reason": "component_unweighted"}

    scale = resolve_school_score_scale(school)
    value = _convert_homework_score(submission.score, assignment.points_possible, scale)

    evaluation, _created = Evaluation.objects.get_or_create(
        academic_year=academic_year,
        term=term,
        subject_assignment=sa,
        student=student,
        defaults={"school": school, "teacher": assignment.teacher},
    )
    setattr(evaluation, field_name, value)
    if getattr(evaluation, "school_id", None) is None:
        evaluation.school = school
    evaluation._audit_change_type = "import"
    evaluation.save()
    return {
        "materialized": True,
        "component": field_name,
        "value": str(value),
        "evaluation_id": evaluation.id,
    }


def open_assignments_for_student(*, school, student, classroom_id: int | None = None):
    """Published, currently-open assignments for a student's classroom (newest due first).

    Used by the student portal list view. Tenant-scoped on ``school`` + the student's
    classroom so a student only ever sees their own class's work.
    """
    cid = classroom_id if classroom_id is not None else getattr(student, "classroom_id", None)
    if cid is None:
        return LMSAssignment.objects.none()
    return (
        LMSAssignment.objects.filter(
            school=school,
            classroom_id=cid,
            status=LMSAssignment.Status.PUBLISHED,
        )
        .select_related("subject")
        .order_by("-due_at", "-id")
    )


def submission_map_for_student(*, school, student, assignment_ids: list[int]) -> dict[int, LMSSubmission]:
    """Map ``assignment_id -> LMSSubmission`` for a student over a set of assignments."""
    if not assignment_ids:
        return {}
    rows = LMSSubmission.objects.filter(
        school=school,
        student=student,
        assignment_id__in=list(assignment_ids),
    ).select_related("assignment")
    return {r.assignment_id: r for r in rows}


# --- Teacher authoring -----------------------------------------------------


@transaction.atomic
def create_assignment(
    *,
    school,
    classroom,
    subject,
    teacher,
    title: str,
    instructions: str = "",
    assignment_type: str = LMSAssignment.AssignmentType.HOMEWORK,
    points_possible=100,
    term=None,
    due_at=None,
    available_at=None,
    attachment=None,
    publish: bool = False,
) -> LMSAssignment:
    """Create a teacher's assignment (DRAFT, or PUBLISHED when ``publish`` is set).

    School is taken from the caller-resolved classroom/teacher context; ``title`` is
    required. Students only ever see PUBLISHED assignments (``open_assignments_for_student``).
    """
    title = (title or "").strip()
    if len(title) < 3:
        raise ValueError("title_min_3_chars")
    status = (
        LMSAssignment.Status.PUBLISHED if publish else LMSAssignment.Status.DRAFT
    )
    if publish and available_at is None:
        available_at = timezone.now()
    return LMSAssignment.objects.create(
        school=school,
        classroom=classroom,
        subject=subject,
        teacher=teacher,
        term=term,
        title=title[:200],
        instructions=(instructions or "")[:8000],
        assignment_type=assignment_type,
        status=status,
        points_possible=points_possible,
        due_at=due_at,
        available_at=available_at,
        attachment=attachment,
    )


@transaction.atomic
def publish_assignment(*, assignment: LMSAssignment) -> LMSAssignment:
    """Move a DRAFT assignment to PUBLISHED so it appears to students."""
    if assignment.status == LMSAssignment.Status.PUBLISHED:
        return assignment
    assignment.status = LMSAssignment.Status.PUBLISHED
    if assignment.available_at is None:
        assignment.available_at = timezone.now()
    assignment.save(update_fields=["status", "available_at", "updated_at"])
    return assignment


def teacher_assignments_for(*, school, teacher):
    """All of a teacher's assignments for this school (newest first), with submission counts."""
    from django.db.models import Count, Q

    return (
        LMSAssignment.objects.filter(school=school, teacher=teacher)
        .select_related("subject", "classroom")
        .annotate(
            submission_count=Count(
                "submissions",
                filter=Q(
                    submissions__status__in=(
                        LMSSubmission.Status.SUBMITTED,
                        LMSSubmission.Status.LATE,
                        LMSSubmission.Status.GRADED,
                        LMSSubmission.Status.RETURNED,
                    )
                ),
                distinct=True,
            ),
            graded_count=Count(
                "submissions",
                filter=Q(submissions__status=LMSSubmission.Status.GRADED),
                distinct=True,
            ),
        )
        .order_by("-created_at", "-id")
    )


def submissions_for_assignment(*, school, assignment):
    """All submissions for an assignment (tenant-scoped), newest submitted first."""
    return (
        LMSSubmission.objects.filter(school=school, assignment=assignment)
        .select_related("student")
        .order_by("-submitted_at", "student__last_name", "student__first_name")
    )


def homework_gradebook_for(*, school, teacher, classroom):
    """Students x published-assignments homework-grade matrix for one of the teacher's classes.

    Independent of ``evals.Evaluation`` BY DESIGN (owner decision 2026-06-26 — "keep
    separate"): homework grades are surfaced here, never written into the seq/exam
    report-card components, so a homework mark can never clobber a continuous-assessment
    score. Returns ``{"assignments": [LMSAssignment, ...], "rows": [{"student", "cells":
    [{assignment, submission, score, status}], "average", "graded_count"}, ...]}``.
    """
    from apps.people.models import StudentProfile

    assignments = list(
        LMSAssignment.objects.filter(
            school=school,
            teacher=teacher,
            classroom=classroom,
            status=LMSAssignment.Status.PUBLISHED,
        )
        .select_related("subject")
        .order_by("due_at", "created_at", "id")
    )
    students = list(
        StudentProfile.objects.filter(
            school=school, classroom=classroom, is_active=True
        ).order_by("last_name", "first_name")
    )

    sub_map: dict[tuple[int, int], LMSSubmission] = {}
    if assignments and students:
        for s in LMSSubmission.objects.filter(
            school=school, assignment__in=assignments, student__in=students
        ).select_related("student"):
            sub_map[(s.student_id, s.assignment_id)] = s

    rows = []
    for student in students:
        cells = []
        graded_scores = []
        for a in assignments:
            sub = sub_map.get((student.id, a.id))
            score = None
            if (
                sub is not None
                and sub.status == LMSSubmission.Status.GRADED
                and sub.score is not None
            ):
                score = sub.score
                graded_scores.append(score)
            cells.append(
                {
                    "assignment": a,
                    "submission": sub,
                    "score": score,
                    "status": sub.status if sub else LMSSubmission.Status.NOT_SUBMITTED,
                }
            )
        average = (sum(graded_scores) / len(graded_scores)) if graded_scores else None
        rows.append(
            {
                "student": student,
                "cells": cells,
                "average": average,
                "graded_count": len(graded_scores),
            }
        )
    return {"assignments": assignments, "rows": rows}


__all__ = [
    "AssignmentClosedError",
    "submit_assignment",
    "grade_submission",
    "open_assignments_for_student",
    "submission_map_for_student",
    "create_assignment",
    "publish_assignment",
    "teacher_assignments_for",
    "submissions_for_assignment",
    "homework_gradebook_for",
]
