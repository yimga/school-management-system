"""Promotion-mapping coverage, and carrying a ladder forward between years.

A ``ClassroomPromotionMapping`` is the only thing that tells a rollover which
classroom in the target year an advancing student lands in. **Nothing derives
it from the structure**, and it must not: cloning a year reproduces the SAME
grades one year later, while the promotion ladder is a different relation
entirely (Form 5A -> Lower Sixth A). Minting identity mappings from a clone
would place every advancing student back in their own grade and report it as a
promotion, which is worse than having no mapping at all.

So the ladder is authored once, by a person, and from then on it is carried
forward -- which is what :func:`carry_forward_promotion_mappings` does.

Two silent failures this module exists to stop:

* A promotion run with **no** mappings moves nobody. ``run_auto_promotion``
  printed a warning and exited 0, so a scheduler, a CI step or an operator
  reading an exit code all saw success.
* A run with **some** mappings skips exactly the students whose classroom was
  missed -- ``skip_reason="no_target_classroom"`` -- one line per student, in
  the middle of a long log, with the summary still reporting a clean run.

:func:`promotion_mapping_coverage` answers both BEFORE the run, per classroom,
and resolves each student's source classroom exactly the way
``promote_student`` does: the latest enrollment row for the source year if
there is one, otherwise the student's own ``classroom`` field. Anything looser
would report a classroom the promotion run never actually visits, and a
blocker that fires on a classroom nobody is in is how a gate gets switched off.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _resolved_source_classroom_ids(source_year, school=None) -> set:
    """Classroom ids ``promote_cohort`` will actually read for this year.

    Mirrors ``promote_student``: the latest ``Enrollment`` row for the source
    year wins, and the student's own ``classroom`` is the fallback. Two bulk
    queries, no per-student round trip.
    """
    from apps.people.models import Enrollment, StudentProfile

    # tenant-isolation-allow: bounded-by-school-owned-academic-year-then-conditional-school
    students = StudentProfile.objects.filter(
        academic_year=source_year, is_active=True
    )
    if school is not None:
        students = students.filter(school=school)
    profile_classroom = dict(students.values_list("id", "classroom_id"))
    if not profile_classroom:
        return set()

    # enrollment_for_year() orders by -entry_date, -id and takes the first, so
    # the SAME ordering is applied here and the first row seen per student wins.
    # tenant-isolation-allow: bounded-by-the-school-scoped-student-set-above
    rows = (
        Enrollment.objects.filter(
            academic_year=source_year,
            student_id__in=list(profile_classroom.keys()),
        )
        .order_by("-entry_date", "-id")
        .values_list("student_id", "classroom_id")
    )
    enrollment_classroom: dict[Any, Any] = {}
    for student_id, classroom_id in rows:
        enrollment_classroom.setdefault(student_id, classroom_id)

    resolved = set()
    for student_id, own_classroom_id in profile_classroom.items():
        classroom_id = enrollment_classroom.get(student_id) or own_classroom_id
        if classroom_id is not None:
            resolved.add(classroom_id)
    return resolved


def promotion_mapping_coverage(source_year, target_year, *, school=None) -> dict:
    """Which populated source classrooms can move their students forward.

    Returns ``{"total", "mapped", "unmapped", "unmapped_classrooms"}`` where
    ``total`` counts only classrooms that actually hold an active student --
    an empty classroom needs no mapping and reporting it would bury the ones
    that do.

    ``unmapped_classrooms`` is a list of ``{"id", "name", "code"}`` so a caller
    can name them rather than print a number the operator cannot act on.
    """
    from .models import Classroom, ClassroomPromotionMapping

    populated_ids = _resolved_source_classroom_ids(source_year, school=school)
    if not populated_ids:
        return {"total": 0, "mapped": 0, "unmapped": 0, "unmapped_classrooms": []}

    # tenant-isolation-allow: bounded-by-source-and-target-year-then-conditional-school
    mapping_qs = ClassroomPromotionMapping.objects.filter(
        source_year=source_year,
        target_year=target_year,
        source_classroom_id__in=populated_ids,
    )
    if school is not None:
        mapping_qs = mapping_qs.filter(school=school)
    mapped_ids = set(mapping_qs.values_list("source_classroom_id", flat=True))

    unmapped_ids = populated_ids - mapped_ids
    unmapped_classrooms = [
        {"id": c.pk, "name": c.name, "code": c.code}
        # tenant-isolation-allow: ids-come-from-the-school-scoped-set-resolved-above
        for c in Classroom.objects.filter(pk__in=unmapped_ids).order_by("name", "code")
    ]
    return {
        "total": len(populated_ids),
        "mapped": len(mapped_ids),
        "unmapped": len(unmapped_ids),
        "unmapped_classrooms": unmapped_classrooms,
    }


def carry_forward_promotion_mappings(
    from_year,
    to_year,
    old_to_new_classroom: dict,
    *,
    school_id: Optional[Any] = None,
) -> int:
    """Shift last year's ladder onto this year's rollover. Returns rows created.

    The ladder that ran INTO ``from_year`` -- mappings whose ``target_year`` is
    ``from_year`` -- says which grade follows which. Applied one year later:

        source = the ``from_year`` classroom with the same NAME as the old
                 mapping's source classroom (that grade, a year on)
        target = ``old_to_new_classroom[old target]`` (the clone the caller
                 just made of the grade that grade advances into)

    Both ends are derived, neither is guessed: a mapping is created only when
    BOTH resolve. If the school has never mapped a ladder there is nothing to
    carry, and this returns 0 rather than inventing one.
    """
    from .models import Classroom, ClassroomPromotionMapping

    if not old_to_new_classroom:
        return 0

    # tenant-isolation-allow: bounded-by-the-school-owned-target-year-fk
    prior = list(
        ClassroomPromotionMapping.objects.filter(target_year=from_year).select_related(
            "source_classroom", "target_classroom"
        )
    )
    if not prior:
        return 0

    # tenant-isolation-allow: bounded-by-the-school-owned-academic-year-fk
    by_name = {}
    for classroom in Classroom.objects.filter(academic_year=from_year):
        by_name.setdefault(classroom.name, classroom)

    created_count = 0
    for mapping in prior:
        source_name = getattr(mapping.source_classroom, "name", None)
        new_source = by_name.get(source_name) if source_name else None
        new_target = old_to_new_classroom.get(mapping.target_classroom_id)
        if new_source is None or new_target is None:
            continue
        # No same-grade check here on purpose. new_source always belongs to
        # from_year and new_target to to_year, so they can never be the same
        # row; and a school whose authored ladder maps a grade onto its own
        # name meant that, so carrying it forward is honouring a decision
        # rather than repeating a mistake.
        _, created = ClassroomPromotionMapping.objects.get_or_create(
            source_year=from_year,
            source_classroom=new_source,
            target_year=to_year,
            defaults={
                "school_id": school_id
                if school_id is not None
                else getattr(new_source, "school_id", None),
                "target_classroom": new_target,
            },
        )
        if created:
            created_count += 1
    if created_count:
        logger.info(
            "carried %s promotion mapping(s) forward from year %s into %s",
            created_count,
            getattr(from_year, "pk", None),
            getattr(to_year, "pk", None),
        )
    return created_count
