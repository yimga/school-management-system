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
        school = getattr(student, "school", None)
        if school is not None:
            from apps.migration_cloud.post_apply_provision import ensure_default_academic_year

            year, _created = ensure_default_academic_year(school)
            if year is not None:
                student.academic_year = year
                student.save(update_fields=["academic_year", "updated_at"])
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


def sync_all_enrollments_for_school(school, *, dry_run: bool = False) -> dict[str, int]:
    """Backfill ``people.Enrollment`` rows from landed student placements."""
    summary = {"examined": 0, "synced": 0, "skipped": 0}
    if school is None:
        return summary
    try:
        from apps.people.models import StudentProfile
    except ImportError:
        return summary

    for student in StudentProfile.objects.filter(school=school, is_active=True).iterator(
        chunk_size=500
    ):
        summary["examined"] += 1
        if getattr(student, "academic_year_id", None) is None:
            from apps.migration_cloud.post_apply_provision import ensure_default_academic_year

            year, _created = ensure_default_academic_year(school)
            if year is not None:
                student.academic_year = year
                if not dry_run:
                    student.save(update_fields=["academic_year", "updated_at"])
        if dry_run:
            summary["synced"] += 1
            continue
        if sync_enrollment_from_student_profile(student) is not None:
            summary["synced"] += 1
        else:
            summary["skipped"] += 1
    return summary
