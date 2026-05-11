"""
Pass 8: importer functions for the Migration Wizard's new domains.

Each importer is a pure function: takes the tenant `school` and an iterable of
mapped row dicts (column → target_field already resolved by the wizard), returns
a result dict shaped like the existing student/grade flow:

    {
        "created": int,
        "updated": int,
        "skipped": int,
        "error_count": int,
        "errors": [str, ...],
        "rollback_snapshot": {...},
    }

Importers that are scaffolded-only (fees / payments — Invoice/Payment models
have complex required FKs and audit constraints out of scope for pass 8.A)
return error_count == row_count with a clear "not yet implemented" message and
leave the model untouched. Pass 8.B will fill those in.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.utils import DatabaseError
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _normalize(value) -> str:
    """Strip + cast to str; treat None as empty."""
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value: str):
    """Accept YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY. Return date or None."""
    value = _normalize(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _empty_result() -> dict:
    return {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "error_count": 0,
        "errors": [],
        "rollback_snapshot": {},
    }


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------


def import_teachers(school, rows: Iterable[dict], *, actor=None) -> dict:
    """Create or update User + TeacherProfile + SchoolMembership for each row."""
    from apps.people.models import TeacherProfile
    from apps.schools.models import SchoolMembership

    result = _empty_result()
    created_ids: list[int] = []
    updated_ids: list[int] = []

    for idx, row in enumerate(rows, start=1):
        email = _normalize(row.get("email")).lower()
        first_name = _normalize(row.get("first_name"))
        last_name = _normalize(row.get("last_name"))
        if not email or not first_name or not last_name:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: email, first_name, last_name are required."
            )
            continue
        username = _normalize(row.get("username")) or email.split("@")[0][:150]
        phone = _normalize(row.get("phone"))
        position = _normalize(row.get("subject_specialty"))
        try:
            with transaction.atomic():
                user, user_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                        "role": User.Role.TEACHER,
                        "is_active": True,
                    },
                )
                if not user_created:
                    user.first_name = first_name or user.first_name
                    user.last_name = last_name or user.last_name
                    user.role = User.Role.TEACHER
                    user.is_active = True
                    user.save(
                        update_fields=["first_name", "last_name", "role", "is_active"]
                    )
                TeacherProfile.objects.update_or_create(
                    user=user,
                    defaults={
                        "school": school,
                        "phone": phone or "",
                        "position_title": position or "",
                        "is_active": True,
                    },
                )
                SchoolMembership.objects.update_or_create(
                    user=user,
                    school=school,
                    defaults={"role": User.Role.TEACHER, "is_primary": True},
                )
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx} ({email}): {exc}")
            continue
        if user_created:
            result["created"] += 1
            created_ids.append(user.pk)
        else:
            result["updated"] += 1
            updated_ids.append(user.pk)

    result["rollback_snapshot"] = {
        "created_user_ids": created_ids,
        "updated_user_ids": updated_ids,
    }
    return result


# ---------------------------------------------------------------------------
# Guardians (parents)
# ---------------------------------------------------------------------------


def import_guardians(school, rows: Iterable[dict], *, actor=None) -> dict:
    """Create or update Parent User + SchoolMembership + StudentGuardian links."""
    from apps.people.models import StudentGuardian, StudentProfile
    from apps.schools.models import SchoolMembership

    result = _empty_result()
    created_user_ids: list[int] = []
    created_link_ids: list[int] = []

    for idx, row in enumerate(rows, start=1):
        email = _normalize(row.get("email")).lower()
        first_name = _normalize(row.get("first_name"))
        last_name = _normalize(row.get("last_name"))
        student_codes_raw = _normalize(row.get("student_codes"))
        if not email or not first_name or not last_name or not student_codes_raw:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: email, first_name, last_name, student_codes are required."
            )
            continue
        student_codes = [
            c.strip() for c in student_codes_raw.replace(";", ",").split(",") if c.strip()
        ]
        students = list(
            StudentProfile.objects.filter(school=school, student_code__in=student_codes)
        )
        missing = set(student_codes) - {s.student_code for s in students}
        if missing:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx} ({email}): student_codes not found: {', '.join(sorted(missing))}."
            )
            continue

        username = _normalize(row.get("username")) or email.split("@")[0][:150]
        phone = _normalize(row.get("phone"))
        relationship_raw = _normalize(row.get("relationship")).upper() or "GUARDIAN"
        relationship = (
            relationship_raw
            if relationship_raw in {"MOTHER", "FATHER", "GUARDIAN", "OTHER"}
            else "OTHER"
        )
        try:
            with transaction.atomic():
                user, user_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                        "role": User.Role.PARENT,
                        "is_active": True,
                    },
                )
                if not user_created:
                    user.first_name = first_name or user.first_name
                    user.last_name = last_name or user.last_name
                    user.role = User.Role.PARENT
                    user.is_active = True
                    user.save(
                        update_fields=["first_name", "last_name", "role", "is_active"]
                    )
                SchoolMembership.objects.update_or_create(
                    user=user,
                    school=school,
                    defaults={"role": User.Role.PARENT, "is_primary": True},
                )
                for student in students:
                    link, link_created = StudentGuardian.objects.update_or_create(
                        guardian_user=user,
                        student=student,
                        defaults={
                            "relationship": relationship,
                            "phone": phone or "",
                            "email": email,
                        },
                    )
                    if link_created:
                        created_link_ids.append(link.pk)
                if user_created:
                    created_user_ids.append(user.pk)
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx} ({email}): {exc}")
            continue
        if user_created:
            result["created"] += 1
        else:
            result["updated"] += 1

    result["rollback_snapshot"] = {
        "created_user_ids": created_user_ids,
        "created_guardian_link_ids": created_link_ids,
    }
    return result


# ---------------------------------------------------------------------------
# Roster (Classroom + Subject + Term — SubjectAssignment deferred to pass 8.B)
# ---------------------------------------------------------------------------


def import_roster(school, rows: Iterable[dict], *, actor=None) -> dict:
    """
    Create or update Classroom, Subject, and Term records.

    SubjectAssignment requires a Specialty FK which not every tenant has
    populated at this stage; that final linkage is deferred to pass 8.B.
    Each row may contribute up to three records (Classroom, Subject, Term).
    """
    from apps.academics.models import (
        AcademicYear,
        Classroom,
        Department,
        Subject,
        Term,
    )

    result = _empty_result()
    created_classrooms: list[int] = []
    created_subjects: list[int] = []
    created_terms: list[int] = []

    # Resolve a default academic year and department once per call.
    active_year = (
        AcademicYear.objects.filter(school=school, is_active=True).order_by("-id").first()
        or AcademicYear.objects.filter(school=school).order_by("-id").first()
    )
    if not active_year:
        result["error_count"] += sum(1 for _ in rows) or 1
        result["errors"].append(
            "No academic year exists for this school. Create one before importing the roster."
        )
        return result

    default_department = (
        Department.objects.filter(school=school).order_by("id").first()
    )

    for idx, row in enumerate(rows, start=1):
        classroom_name = _normalize(row.get("classroom_name"))
        subject_code = _normalize(row.get("subject_code"))
        subject_name = _normalize(row.get("subject_name")) or subject_code
        term_name = _normalize(row.get("term_name"))
        if not classroom_name or not subject_code:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: classroom_name and subject_code are required."
            )
            continue
        try:
            with transaction.atomic():
                department = default_department or Department.objects.create(
                    school=school,
                    code=f"{school.slug or 'sch'}-GEN",
                    name="General",
                )
                classroom, classroom_created = Classroom.objects.update_or_create(
                    code=f"{school.slug or 'sch'}-{classroom_name}"[:30],
                    defaults={
                        "school": school,
                        "academic_year": active_year,
                        "department": department,
                        "name": classroom_name,
                    },
                )
                if classroom_created:
                    created_classrooms.append(classroom.pk)
                subject, subject_created = Subject.objects.get_or_create(
                    school=school,
                    name=subject_name,
                    defaults={"category": Subject.Category.GENERAL},
                )
                if subject_created:
                    created_subjects.append(subject.pk)
                if term_name:
                    term, term_created = Term.objects.get_or_create(
                        school=school,
                        academic_year=active_year,
                        name=term_name[:60],
                    )
                    if term_created:
                        created_terms.append(term.pk)
                result["created"] += 1
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx}: {exc}")
            continue

    result["rollback_snapshot"] = {
        "created_classroom_ids": created_classrooms,
        "created_subject_ids": created_subjects,
        "created_term_ids": created_terms,
    }
    result["errors"].append(
        "Note: SubjectAssignment rows (linking classroom × subject × term × specialty × teacher) "
        "are not yet auto-created by this importer; create them via the Academics admin or wait for pass 8.B."
    )
    return result


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------


def import_attendance(school, rows: Iterable[dict], *, actor=None) -> dict:
    """Bulk-create Attendance records via student_code + classroom lookup."""
    from apps.academics.models import Attendance, Classroom
    from apps.people.models import StudentProfile

    result = _empty_result()
    created_ids: list[int] = []
    valid_statuses = {choice[0] for choice in Attendance.Status.choices}

    for idx, row in enumerate(rows, start=1):
        student_code = _normalize(row.get("student_code"))
        date_value = _parse_date(_normalize(row.get("date")))
        status = _normalize(row.get("status")).lower() or Attendance.Status.PRESENT
        if not student_code or date_value is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: student_code and a valid date (YYYY-MM-DD) are required."
            )
            continue
        if status not in valid_statuses:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: invalid status '{status}' (must be one of {sorted(valid_statuses)})."
            )
            continue
        student = (
            StudentProfile.objects.filter(school=school, student_code=student_code)
            .select_related("classroom")
            .first()
        )
        if student is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: student_code '{student_code}' not found for this school."
            )
            continue
        classroom = getattr(student, "classroom", None)
        if classroom is None:
            classroom = (
                Classroom.objects.filter(school=school).order_by("id").first()
            )
        if classroom is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: no classroom available to anchor the attendance row."
            )
            continue
        try:
            record, created = Attendance.objects.update_or_create(
                student=student,
                classroom=classroom,
                date=date_value,
                defaults={
                    "school": school,
                    "status": status,
                    "remarks": _normalize(row.get("remarks"))[:255],
                },
            )
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx} ({student_code}): {exc}")
            continue
        if created:
            result["created"] += 1
            created_ids.append(record.pk)
        else:
            result["updated"] += 1

    result["rollback_snapshot"] = {"created_attendance_ids": created_ids}
    return result


# ---------------------------------------------------------------------------
# Fees and Payments (pass 8.B scaffolds — record-only, no Invoice/Payment writes)
# ---------------------------------------------------------------------------


def import_fees(school, rows: Iterable[dict], *, actor=None) -> dict:
    """
    Pass 8.A: row-count audit only. The Invoice model has audit / FK / immutability
    constraints (Part F 25.1) that demand a dedicated service; that lands in 8.B.
    """
    result = _empty_result()
    row_list = list(rows)
    result["skipped"] = len(row_list)
    result["errors"].append(
        "Fee imports are recorded in the migration audit log but not yet persisted to "
        "Invoice; the dedicated FeeImportService lands in pass 8.B."
    )
    result["rollback_snapshot"] = {"deferred_row_count": len(row_list)}
    return result


def import_payments(school, rows: Iterable[dict], *, actor=None) -> dict:
    """
    Pass 8.A: row-count audit only. Payment writes need Invoice resolution +
    currency normalization + balance recalculation; deferred to 8.B.
    """
    result = _empty_result()
    row_list = list(rows)
    result["skipped"] = len(row_list)
    result["errors"].append(
        "Payment imports are recorded in the migration audit log but not yet persisted to "
        "Payment; the dedicated PaymentImportService lands in pass 8.B."
    )
    result["rollback_snapshot"] = {"deferred_row_count": len(row_list)}
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


IMPORTERS = {
    "teachers": import_teachers,
    "guardians": import_guardians,
    "roster": import_roster,
    "attendance": import_attendance,
    "fees": import_fees,
    "payments": import_payments,
}


def run_importer(migration_type: str, school, rows: Iterable[dict], *, actor=None) -> dict:
    """Look up the importer for `migration_type` and invoke it. Raises KeyError on unknown."""
    importer = IMPORTERS[migration_type]
    return importer(school, rows, actor=actor)
