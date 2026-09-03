"""Teaching graph closure — SubjectAssignment grid + TeacherAssignment RBAC links.

Closes the gap between catalog/people landers and operational gradebook access:
  • SpecialtySubject (curriculum) vs SubjectAssignment (grid cell)
  • TeacherProfile + DFV hints vs TeacherAssignment (portal + ReBAC)
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _parse_name_list(raw: str) -> list[str]:
    if not raw:
        return []
    parts: list[str] = []
    for chunk in str(raw).replace(";", ",").split(","):
        name = chunk.strip()
        if name:
            parts.append(name)
    return parts


def assess_teaching_graph_readiness(school) -> dict[str, Any]:
    """Counts that explain whether grades and teacher portal can work."""
    from apps.academics.models import SubjectAssignment
    from apps.evals.models import TeacherAssignment
    from apps.metadata.models import DynamicFieldValue
    from apps.people.models import StudentProfile, TeacherProfile

    if school is None:
        return {"ready": False, "reason": "no_school"}

    students = StudentProfile.objects.filter(school=school, is_active=True)
    total_students = students.count()
    unplaced_class = students.filter(classroom__isnull=True).count()
    unplaced_spec = students.filter(specialty__isnull=True).count()
    assignment_count = SubjectAssignment.objects.filter(school=school).count()
    teacher_assign_count = TeacherAssignment.objects.filter(
        school=school, is_active=True
    ).count()
    teachers = TeacherProfile.objects.filter(school=school).count()
    hinted = DynamicFieldValue.objects.filter(
        school=school,
        entity_type="staff",
        field_key__in=("teaching_subjects", "teaching_classrooms"),
    ).values("entity_id").distinct().count()

    gradeable_pairs = students.exclude(classroom__isnull=True).exclude(
        specialty__isnull=True
    ).count()

    return {
        "students_active": total_students,
        "students_missing_classroom": unplaced_class,
        "students_missing_specialty": unplaced_spec,
        "students_with_class_and_specialty": gradeable_pairs,
        "subject_assignments": assignment_count,
        "teacher_assignments_active": teacher_assign_count,
        "teachers": teachers,
        "staff_with_teaching_hints": hinted,
        "ready_for_grades": gradeable_pairs > 0 and assignment_count > 0,
        "ready_for_teacher_portal": teacher_assign_count > 0,
    }


def ensure_teaching_graph_for_school(school, *, dry_run: bool = False) -> dict[str, Any]:
    """Idempotently rebuild curriculum links and student-driven teaching grid."""
    if school is None:
        return {"skipped": True, "reason": "no_school"}
    if dry_run:
        return {"skipped": True, "reason": "dry_run", "would_run": True}

    from apps.academics.structure_provisioning import (
        ensure_specialty_curriculum,
        provision_per_specialty_grid,
        provision_teaching_grid_for_school,
    )

    summary: dict[str, Any] = {"phase": "teaching_graph_provision"}
    try:
        summary["curriculum"] = ensure_specialty_curriculum(school)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "teaching_graph: curriculum failed school=%s: %s",
            getattr(school, "pk", "?"),
            exc,
            exc_info=True,
        )
        summary["curriculum"] = f"error: {type(exc).__name__}"

    try:
        summary["general_grid"] = provision_teaching_grid_for_school(school)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "teaching_graph: general grid failed school=%s: %s",
            getattr(school, "pk", "?"),
            exc,
            exc_info=True,
        )
        summary["general_grid"] = f"error: {type(exc).__name__}"

    try:
        summary["specialty_grid"] = provision_per_specialty_grid(school)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "teaching_graph: specialty grid failed school=%s: %s",
            getattr(school, "pk", "?"),
            exc,
            exc_info=True,
        )
        summary["specialty_grid"] = f"error: {type(exc).__name__}"

    summary["readiness_after"] = assess_teaching_graph_readiness(school)
    return summary


def _dominant_specialty_id(school, classroom_id) -> Optional[int]:
    """Return the specialty id when one trade clearly owns the classroom."""
    from apps.people.models import StudentProfile

    spec_ids = list(
        StudentProfile.objects.filter(
            school=school, classroom_id=classroom_id, is_active=True
        )
        .exclude(specialty__isnull=True)
        .values_list("specialty_id", flat=True)
    )
    if not spec_ids:
        return None
    counts = Counter(spec_ids)
    top_id, top_n = counts.most_common(1)[0]
    if len(counts) == 1:
        return top_id
    second_n = counts.most_common(2)[1][1] if len(counts) > 1 else 0
    if top_n >= second_n * 2:
        return top_id
    return None


def link_teacher_assignments_from_import_hints(
    school, *, dry_run: bool = False
) -> dict[str, Any]:
    """Create ``TeacherAssignment`` rows when staff DFV hints are unambiguous."""
    from apps.academics.models import AcademicYear, Classroom, Subject, SubjectAssignment
    from apps.evals.models import TeacherAssignment
    from apps.metadata.models import DynamicFieldValue
    from apps.people.models import TeacherProfile

    if school is None:
        return {"skipped": True, "reason": "no_school"}

    year = (
        AcademicYear.objects.filter(school=school, is_active=True).first()
        or AcademicYear.objects.filter(school=school).order_by("-start_date").first()
    )
    if year is None:
        return {"skipped": True, "reason": "no_academic_year"}

    created = 0
    skipped_no_hints = 0
    skipped_ambiguous = 0
    skipped_no_assignment = 0
    skipped_existing = 0

    teachers = TeacherProfile.objects.filter(school=school).select_related("user")
    for teacher in teachers:
        dfv_rows = DynamicFieldValue.objects.filter(
            school=school,
            entity_type="staff",
            entity_id=str(teacher.pk),
            field_key__in=("teaching_subjects", "teaching_classrooms"),
        )
        hints = {
            row.field_key: str((row.value_json or {}).get("v") or "")
            for row in dfv_rows
        }
        class_names = _parse_name_list(hints.get("teaching_classrooms", ""))
        subject_names = _parse_name_list(hints.get("teaching_subjects", ""))
        if not class_names or not subject_names:
            skipped_no_hints += 1
            continue

        for class_name in class_names:
            classroom = (
                Classroom.objects.filter(school=school, name__iexact=class_name).first()
                or Classroom.objects.filter(school=school, code__iexact=class_name).first()
            )
            if classroom is None:
                skipped_no_assignment += 1
                continue

            specialty_id = _dominant_specialty_id(school, classroom.pk)

            for subject_name in subject_names:
                subject = (
                    Subject.objects.filter(school=school, name__iexact=subject_name).first()
                    or Subject.objects.filter(
                        school=school, code__iexact=subject_name
                    ).first()
                )
                if subject is None:
                    skipped_no_assignment += 1
                    continue

                qs = SubjectAssignment.objects.filter(
                    school=school,
                    academic_year=year,
                    classroom=classroom,
                    subject=subject,
                )
                if specialty_id is not None:
                    qs = qs.filter(specialty_id=specialty_id)

                assignments = list(qs)
                if not assignments:
                    skipped_no_assignment += 1
                    continue
                if specialty_id is None and len({a.specialty_id for a in assignments}) > 1:
                    skipped_ambiguous += 1
                    continue

                for assignment in assignments:
                    exists = TeacherAssignment.objects.filter(
                        school=school,
                        teacher=teacher,
                        academic_year=year,
                        subject_assignment=assignment,
                        is_active=True,
                    ).exists()
                    if exists:
                        skipped_existing += 1
                        continue
                    if dry_run:
                        created += 1
                        continue
                    TeacherAssignment.objects.create(
                        school=school,
                        teacher=teacher,
                        academic_year=year,
                        subject_assignment=assignment,
                        is_active=True,
                    )
                    created += 1

    return {
        "teacher_assignments_created": created,
        "skipped_no_hints": skipped_no_hints,
        "skipped_ambiguous": skipped_ambiguous,
        "skipped_no_assignment": skipped_no_assignment,
        "skipped_existing": skipped_existing,
        "readiness_after": assess_teaching_graph_readiness(school),
    }


def ensure_teaching_graph_closure(
    school, *, dry_run: bool = False
) -> dict[str, Any]:
    """Full teaching-graph pass: grid provision + conservative teacher RBAC links."""
    readiness_before = assess_teaching_graph_readiness(school)
    provision = ensure_teaching_graph_for_school(school, dry_run=dry_run)
    teacher_links = link_teacher_assignments_from_import_hints(
        school, dry_run=dry_run
    )
    return {
        "readiness_before": readiness_before,
        "provision": provision,
        "teacher_links": teacher_links,
        "readiness_after": assess_teaching_graph_readiness(school),
    }


def ensure_teaching_graph_closure_for_bundle(bundle, *, dry_run: bool = False) -> dict[str, Any]:
    """Bundle-scoped wrapper used by autopilot and post-apply hooks."""
    school = getattr(bundle, "school", None)
    if school is None:
        return {"skipped": True, "reason": "no_school"}
    return ensure_teaching_graph_closure(school, dry_run=dry_run)
