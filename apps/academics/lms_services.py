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

from datetime import date as date_type
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.academics.models_lms import LMSAssignment, LMSSubmission


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
    return submission


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


__all__ = [
    "AssignmentClosedError",
    "submit_assignment",
    "grade_submission",
    "open_assignments_for_student",
    "submission_map_for_student",
]
