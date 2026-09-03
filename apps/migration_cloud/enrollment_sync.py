"""Keep ``people.Enrollment`` in sync when Migration Cloud writes placement on students."""

from __future__ import annotations

from typing import Any, Optional


def sync_enrollment_from_student_profile(student) -> Optional[Any]:
    """Project a landed student's placement onto the enrollment SOT.

    Migration landers still write legacy ``StudentProfile`` FKs first (compat
    with ~180 readers). This helper opens or amends the active enrollment row
    so history, rollover, and ``current_classroom`` stay truthful.
    """
    if student is None:
        return None
    if getattr(student, "academic_year_id", None) is None:
        return None

    from apps.people.enrollment_services import ensure_enrollment, set_placement

    enrollment = set_placement(student)
    if enrollment is None:
        enrollment = ensure_enrollment(student)
    if enrollment is None:
        return None

    changed: list[str] = []
    specialty_id = getattr(student, "specialty_id", None)
    if specialty_id and enrollment.specialty_id != specialty_id:
        enrollment.specialty_id = specialty_id
        changed.append("specialty")
    section = (getattr(student, "section", None) or "").strip()
    if section and enrollment.section != section:
        enrollment.section = section
        changed.append("section")
    if changed:
        changed.append("updated_at")
        enrollment.save(update_fields=changed)

    enrollment.sync_student_row()
    return enrollment
