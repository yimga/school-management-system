"""
Year setup utilities: clone previous academic year (terms, classrooms, subject assignments).
Used by Workflow Center and backend year-setup flows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from .models import AcademicYear, Term, Classroom, SubjectAssignment
from apps.reports.models import PromotionRule

if TYPE_CHECKING:
    pass


def _year_suffix(academic_year: AcademicYear) -> str:
    """Short suffix for year name, e.g. 2025/2026 -> 2526."""
    name = (academic_year.name or "").replace("/", "").replace(" ", "")[:8]
    return name or str(academic_year.id)


def clone_academic_year(
    from_year: AcademicYear,
    to_year: AcademicYear,
    *,
    copy_terms: bool = True,
    copy_classrooms: bool = True,
    copy_subject_assignments: bool = True,
    copy_promotion_rules: bool = True,
) -> dict:
    """
    Copy structure from from_year to to_year.
    - Terms: same name, position, custom_label; start/end dates are copied (operator can adjust in admin).
    - Classrooms: same name, department; code = original_code + '-' + year_suffix to keep uniqueness.
    - SubjectAssignments: recreated for to_year using new term/classroom mapping.
    - PromotionRule: copied for to_year (classroom=None or mapped to new classroom).

    Returns dict with counts: terms_created, classrooms_created, subject_assignments_created, promotion_rules_created.
    """
    # Defence in depth against a cross-school clone. The view scopes both years to
    # request.school, but this service is also reachable from management commands and
    # future callers; a tenant SCHEMA can hold several Schools (multi-campus) and RLS
    # deployments share one schema outright, so "same tenant" does not imply "same
    # school". Copying one school's structure into another's year would be silent,
    # irreversible data contamination - refuse loudly instead.
    from_school_id = getattr(from_year, "school_id", None)
    to_school_id = getattr(to_year, "school_id", None)
    if from_school_id is not None and to_school_id is not None:
        if from_school_id != to_school_id:
            raise ValueError(
                "Cannot clone across schools: "
                f"{from_year.name} belongs to school {from_school_id} but "
                f"{to_year.name} belongs to school {to_school_id}."
            )
    if from_year.pk is not None and from_year.pk == to_year.pk:
        raise ValueError("Source and target academic year must be different.")

    suffix = _year_suffix(to_year)
    old_to_new_classroom: dict[int, Classroom] = {}
    old_to_new_term: dict[int, Term] = {}
    stats = {
        "terms_created": 0,
        "classrooms_created": 0,
        "subject_assignments_created": 0,
        "promotion_rules_created": 0,
    }

    with transaction.atomic():
        if copy_terms:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            for t in Term.objects.filter(academic_year=from_year).order_by(
                "position", "start_date"
            ):
                new_term, created = Term.objects.get_or_create(
                    academic_year=to_year,
                    name=t.name,
                    defaults={
                        "custom_label": t.custom_label or "",
                        "position": t.position,
                        "start_date": t.start_date,
                        "end_date": t.end_date,
                        "is_active": False,
                    },
                )
                old_to_new_term[t.id] = new_term
                if created:
                    stats["terms_created"] += 1

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        if copy_classrooms:
            for c in Classroom.objects.filter(academic_year=from_year).select_related(
                "department"
            ):
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                new_code = f"{c.code}-{suffix}"
                # Ensure globally unique code
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                if Classroom.objects.filter(code=new_code).exists():
                    new_code = f"{c.code}-{suffix}-{to_year.id}"
                new_class, created = Classroom.objects.get_or_create(
                    academic_year=to_year,
                    code=new_code,
                    defaults={
                        "name": c.name,
                        "department": c.department,
                        "allows_third_term": c.allows_third_term,
                    },
                )
                old_to_new_classroom[c.id] = new_class
                if created:
                    stats["classrooms_created"] += 1
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        if copy_subject_assignments and old_to_new_term and old_to_new_classroom:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            for sa in SubjectAssignment.objects.filter(
                academic_year=from_year
            ).select_related("term", "classroom", "specialty", "subject"):
                new_term = old_to_new_term.get(sa.term_id)
                new_class = old_to_new_classroom.get(sa.classroom_id)
                if not new_term or not new_class:
                    continue
                _, created = SubjectAssignment.objects.get_or_create(
                    academic_year=to_year,
                    term=new_term,
                    classroom=new_class,
                    specialty=sa.specialty,
                    subject=sa.subject,
                    defaults={"coefficient": sa.coefficient},
                )
                if created:
                    stats["subject_assignments_created"] += 1

        if copy_promotion_rules:
            for pr in PromotionRule.objects.filter(
                academic_year=from_year
            ).select_related("classroom"):
                new_class = (
                    old_to_new_classroom.get(pr.classroom_id)
                    if pr.classroom_id
                    else None
                )
                _, created = PromotionRule.objects.get_or_create(
                    academic_year=to_year,
                    classroom=new_class,
                    defaults={
                        "promotion_average": pr.promotion_average,
                        "demotion_average": pr.demotion_average,
                    },
                )
                if created:
                    stats["promotion_rules_created"] += 1

    return stats
