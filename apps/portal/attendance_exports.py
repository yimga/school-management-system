"""
North Star SLICE 6 — tenant-scoped student attendance CSV export (academics.Attendance).

Teacher users are restricted to classrooms from active TeacherAssignments.
School staff and broad roles export with full in-tenant filters.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
from typing import Any, Iterator

from django.db.models import QuerySet
from django.http import HttpResponse
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import Attendance, Classroom
from apps.schools.tenant_access import safe_queryset_for_school, user_belongs_to_school


MAX_STUDENT_ATTENDANCE_EXPORT_ROWS = 10000

CSV_COLUMNS = (
    "date",
    "student_id",
    "student_name",
    "student_code",
    "admission_number",
    "classroom_id",
    "classroom_name",
    "status",
    "remarks",
    "updated_at",
)


@dataclass
class StudentAttendanceExportFilters:
    start_date: date
    end_date: date
    classroom_id: int | None = None
    student_id: int | None = None


def user_can_access_student_attendance_export(user: Any) -> bool:
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    role = (getattr(user, "role", "") or "").upper()
    allowed = {
        User.Role.ADMIN,
        User.Role.LEADERSHIP,
        User.Role.IT_ADMIN,
        User.Role.PRINCIPAL,
        User.Role.VICE_PRINCIPAL,
        User.Role.TEACHER,
    }
    if role in allowed:
        return True
    has_fp = getattr(user, "has_feature_permission", None)
    if callable(has_fp) and has_fp("attendance.manage"):
        return True
    return False


def _teacher_scoped_classroom_ids(user: Any, school: Any) -> frozenset[int]:
    """Classroom IDs the teacher may see for student attendance (via TeacherAssignment)."""
    from apps.evals.models import TeacherAssignment

    tp = getattr(user, "teacher_profile", None)
    if not tp or not school:
        return frozenset()
    ids = (
        TeacherAssignment.objects.filter(
            teacher=tp,
            is_active=True,
            subject_assignment__classroom__school_id=school.id,
        )
        .values_list("subject_assignment__classroom_id", flat=True)
        .distinct()
    )
    return frozenset(int(x) for x in ids if x is not None)


def _user_is_teacher_only_scoped(user: Any) -> bool:
    role = (getattr(user, "role", "") or "").upper()
    if role != User.Role.TEACHER:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return False
    return True


def parse_export_filters_from_get(get_data: Any) -> tuple[StudentAttendanceExportFilters | None, str | None]:
    """Parse and validate ?start_date= &end_date= &classroom= &student= from query dict."""
    today = timezone.localdate()

    def _parse_one(key: str) -> date | None:
        raw = (get_data.get(key) or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except (ValueError, TypeError):
            return None

    end = _parse_one("end_date")
    start = _parse_one("start_date")
    if start is None and end is None:
        end = today
        start = end - timedelta(days=30)
    elif start is None:
        if end is None:
            return None, "Invalid or incomplete date range."
        start = end - timedelta(days=30)
    elif end is None:
        end = start + timedelta(days=30)

    if start is None or end is None:
        return None, "Invalid or incomplete date range."
    if start > end:
        return None, "Start date must be on or before end date."

    classroom_raw = (get_data.get("classroom_id") or get_data.get("classroom") or "").strip()
    student_raw = (get_data.get("student_id") or get_data.get("student") or "").strip()
    classroom_id: int | None = None
    student_id: int | None = None
    if classroom_raw:
        try:
            classroom_id = int(classroom_raw)
        except (TypeError, ValueError):
            return None, "Invalid classroom filter."
    if student_raw:
        try:
            student_id = int(student_raw)
        except (TypeError, ValueError):
            return None, "Invalid student filter."

    assert start is not None and end is not None  # assert-allow: type-narrowing only; runtime guard at the early-return above
    return (
        StudentAttendanceExportFilters(
            start_date=start,
            end_date=end,
            classroom_id=classroom_id,
            student_id=student_id,
        ),
        None,
    )


def _safe_filename_part(s: str) -> str:
    s = (s or "").strip() or "school"
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", s)[:80]


def build_student_attendance_export_queryset(
    school: Any,
    user: Any,
    filters: StudentAttendanceExportFilters,
) -> tuple[QuerySet, str | None]:
    """
    Return Attendance queryset scoped to the school and the user's role, or (empty, error).
    """
    if not school:
        return Attendance.objects.none(), "School context is required."
    if not user_belongs_to_school(user, school):
        return Attendance.objects.none(), "Not a member of this school."
    if not user_can_access_student_attendance_export(user):
        return Attendance.objects.none(), "Not authorized for student attendance export."

    qs: QuerySet = safe_queryset_for_school(Attendance.objects.all(), school).filter(
        date__gte=filters.start_date,
        date__lte=filters.end_date,
    )

    allowed_teacher: frozenset[int] | None = None
    if _user_is_teacher_only_scoped(user):
        allowed_teacher = _teacher_scoped_classroom_ids(user, school)
        if not allowed_teacher:
            return qs.none(), None
        qs = qs.filter(classroom_id__in=allowed_teacher)
        if filters.classroom_id is not None and filters.classroom_id not in allowed_teacher:
            return qs.none(), "You are not assigned to the selected classroom."

    if filters.classroom_id is not None:
        qs = qs.filter(classroom_id=filters.classroom_id)
    if filters.student_id is not None:
        qs = qs.filter(student_id=filters.student_id)

    qs = (
        qs.filter(student__school_id=school.id)
        .select_related("student", "classroom", "school")
        .order_by("date", "classroom__name", "student__last_name", "student__first_name")
        .distinct()
    )
    return qs, None


def serialize_student_attendance_csv_rows(qs: QuerySet) -> Iterator[list[str | int]]:
    for a in qs[:MAX_STUDENT_ATTENDANCE_EXPORT_ROWS]:
        st = a.student
        name = ""
        if st:
            name = f"{(st.last_name or '').strip()} {(st.first_name or '').strip()}".strip() or str(
                st
            )
        yield [
            a.date.isoformat() if a.date else "",
            str(a.student_id),
            name,
            getattr(st, "student_code", "") or "",
            getattr(st, "admission_number", "") or "",
            str(a.classroom_id),
            (a.classroom.name if a.classroom else "") or "",
            a.get_status_display(),
            (a.remarks or "")[:255],
            a.updated_at.isoformat() if getattr(a, "updated_at", None) else "",
        ]


def build_student_attendance_csv_response(
    qs: QuerySet,
    school: Any,
    filters: StudentAttendanceExportFilters,
) -> HttpResponse:
    total = qs.count()
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for row in serialize_student_attendance_csv_rows(qs):
        w.writerow(row)

    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    slug = _safe_filename_part(getattr(school, "slug", None) or "school")
    fn = f"student_attendance_{slug}_{filters.start_date.isoformat()}_{filters.end_date.isoformat()}.csv"
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    if total > MAX_STUDENT_ATTENDANCE_EXPORT_ROWS:
        resp["X-Export-Truncated"] = "1"
    return resp


def get_classroom_options_for_export(school: Any, user: Any, year: Any) -> list[Classroom]:
    """Classrooms the user may filter on for the active academic year."""
    if not school or not year:
        return []
    base = list(
        Classroom.objects.filter(school_id=school.id, academic_year=year).order_by("name")
    )
    if _user_is_teacher_only_scoped(user):
        allow = _teacher_scoped_classroom_ids(user, school)
        return [c for c in base if c.id in allow]
    return base


def get_student_options_for_export(school: Any, user: Any, limit: int = 500):
    """Student queryset for optional export filter (scoped for teachers)."""
    from apps.people.models import StudentProfile

    if not school:
        return StudentProfile.objects.none()
    qs = StudentProfile.objects.filter(school_id=school.id, is_active=True).order_by(
        "last_name", "first_name"
    )
    if _user_is_teacher_only_scoped(user):
        allow = _teacher_scoped_classroom_ids(user, school)
        if not allow:
            return qs.none()
        qs = qs.filter(classroom_id__in=allow)
    return qs[:limit]
