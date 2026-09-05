"""Backfill student classroom placement after import gaps.

``StudentLander._link_student_classroom`` is best-effort and never quarantines.
When department/year provisioning fails, students land without ``classroom_id``
even though ``class_source`` was stored on the row. This module replays placement
from that preserved label so classroom rosters match the roster file.
"""
from __future__ import annotations

from typing import Any

from django.db import DatabaseError


def _class_label_for_student(student) -> str:
    attrs = getattr(student, "custom_attributes", None) or {}
    if isinstance(attrs, dict):
        for key in ("class_source", "grade_level", "classroom", "form", "class"):
            val = str(attrs.get(key) or "").strip()
            if val:
                return val
    try:
        from apps.metadata.models import DynamicFieldValue
    except ImportError:
        return ""
    school = getattr(student, "school", None)
    qs = DynamicFieldValue.objects.filter(
        entity_type="student",
        entity_id=str(student.pk),
        field_key="class_source",
    )
    if school is not None:
        qs = qs.filter(school=school)
    row = qs.order_by("-updated_at").first()
    if row is None:
        return ""
    value = row.value_json
    if isinstance(value, str):
        return value.strip()
    if value is not None:
        return str(value).strip()
    return ""


def backfill_student_classrooms_for_school(school, *, dry_run: bool = False) -> dict[str, int]:
    """Place students with a saved class label but no ``classroom_id``."""
    summary = {"examined": 0, "placed": 0, "skipped": 0, "failed": 0}
    if school is None:
        return summary
    try:
        from apps.people.models import StudentProfile
    except ImportError:
        return summary

    from apps.migration_cloud.enrollment_sync import sync_enrollment_from_student_profile
    from apps.migration_cloud.landers.base import LanderResult
    from apps.migration_cloud.landers.student_lander import _link_student_classroom

    model_fields = {f.name for f in StudentProfile._meta.get_fields()}  # noqa: SLF001

    for student in StudentProfile.objects.filter(
        school=school, is_active=True, classroom_id__isnull=True
    ).iterator(chunk_size=200):
        summary["examined"] += 1
        label = _class_label_for_student(student)
        if not label:
            summary["skipped"] += 1
            continue
        if dry_run:
            summary["placed"] += 1
            continue
        row = {"grade_level": label, "classroom": label}
        ctx = type(
            "Ctx",
            (),
            {"school": school, "artifact_id": "backfill"},
        )()
        result = LanderResult()
        before_id = getattr(student, "classroom_id", None)
        try:
            _link_student_classroom(student, row, ctx, model_fields, result)
            student.refresh_from_db()
        except (DatabaseError, TypeError, ValueError):
            summary["failed"] += 1
            continue
        if getattr(student, "classroom_id", None) and student.classroom_id != before_id:
            summary["placed"] += 1
            try:
                sync_enrollment_from_student_profile(student)
            except (ImportError, DatabaseError, TypeError, ValueError):
                pass
        else:
            summary["skipped"] += 1
    return summary
