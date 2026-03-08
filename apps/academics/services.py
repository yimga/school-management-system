"""Small, shared domain helpers.

Keeping these in one place avoids copy/paste drift across apps.
"""

from __future__ import annotations

from typing import Optional, Tuple

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.people.models import StudentProfile
from .models import AcademicYear, Term
from .models import DegreeProgram, TransferCourseEquivalency, TransferCredit


def get_active_year_and_term(*, school=None) -> Tuple[Optional[AcademicYear], Optional[Term]]:
    """Return (active_year, active_term) if configured, optionally scoped to one school."""
    years = AcademicYear.objects.filter(is_active=True)
    if school is not None and hasattr(AcademicYear, "school_id"):
        years = years.filter(school=school)
    year = years.order_by("id").first()
    term = (
        Term.objects.filter(is_active=True, academic_year=year).order_by("id").first()
        if year
        else None
    )
    return year, term


def _normalize_course_code(value: str) -> str:
    return (value or "").strip().upper()


def submit_transfer_equivalency_request(
    *,
    student: StudentProfile,
    external_course_code: str,
    internal_course_code: str,
    program: DegreeProgram | None = None,
    transfer_credit: TransferCredit | None = None,
    requested_by=None,
    request_notes: str = "",
) -> TransferCourseEquivalency:
    """Create a pending transfer equivalency request."""
    if program and program.school_id != student.school_id:
        raise ValidationError("Program and student must belong to the same school.")
    if transfer_credit and transfer_credit.student_id != student.id:
        raise ValidationError("Transfer credit must belong to the same student.")

    school = student.school or (program.school if program else None)
    if school is None:
        raise ValidationError("Student must belong to a school.")

    external = _normalize_course_code(external_course_code)
    internal = _normalize_course_code(internal_course_code)
    if not external or not internal:
        raise ValidationError("Both external and internal course codes are required.")

    return TransferCourseEquivalency.objects.create(
        school=school,
        student=student,
        program=program,
        transfer_credit=transfer_credit,
        external_course_code=external,
        internal_course_code=internal,
        requested_by=requested_by,
        request_notes=request_notes or "",
        status=TransferCourseEquivalency.Status.PENDING,
    )


def review_transfer_equivalency_request(
    mapping: TransferCourseEquivalency,
    *,
    approve: bool,
    reviewed_by,
    reviewer_notes: str = "",
) -> TransferCourseEquivalency:
    """Approve or reject a transfer equivalency request."""
    mapping.status = (
        TransferCourseEquivalency.Status.APPROVED
        if approve
        else TransferCourseEquivalency.Status.REJECTED
    )
    mapping.reviewed_by = reviewed_by
    mapping.reviewer_notes = reviewer_notes or ""
    mapping.reviewed_at = timezone.now()
    mapping.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewer_notes",
            "reviewed_at",
            "updated_at",
        ]
    )
    return mapping


def get_approved_transfer_equivalency_map(
    *,
    student: StudentProfile,
    program: DegreeProgram | None = None,
) -> dict[str, list[str]]:
    """
    Return approved mappings as {internal_course_code: [external_course_code, ...]}.

    Program-scoped mappings are included when `program` matches; program-null mappings
    are always included for that student.
    """
    queryset = TransferCourseEquivalency.objects.filter(
        student=student,
        status=TransferCourseEquivalency.Status.APPROVED,
    )
    if program is not None:
        queryset = queryset.filter(Q(program=program) | Q(program__isnull=True))

    out: dict[str, list[str]] = {}
    for row in queryset:
        internal = _normalize_course_code(row.internal_course_code)
        external = _normalize_course_code(
            row.external_course_code
            or (row.transfer_credit.course_code if row.transfer_credit_id else "")
        )
        if not internal or not external:
            continue
        bucket = out.setdefault(internal, [])
        if external not in bucket:
            bucket.append(external)
    return out
