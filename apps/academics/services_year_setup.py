"""
Year setup utilities: clone previous academic year (terms, classrooms, subject assignments).
Used by Workflow Center and backend year-setup flows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from .models import AcademicYear, Term, Classroom, SubjectAssignment
from .promotion_mappings import carry_forward_promotion_mappings
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
    copy_promotion_mappings: bool = True,
) -> dict:
    """
    Copy structure from from_year to to_year.
    - Terms: same name, position, custom_label; start/end dates are copied (operator can adjust in admin).
    - Classrooms: same name, department; code = original_code + '-' + year_suffix
      to keep the code unique WITHIN THE SCHOOL (Classroom.code is unique per
      school, not globally). Every cloned row is stamped with the owning school.
    - SubjectAssignments: recreated for to_year using new term/classroom mapping.
    - PromotionRule: copied for to_year (classroom=None or mapped to new classroom).
    - ClassroomPromotionMapping: last year's LADDER shifted forward one year, so a
      school authors "Form 5A advances into Lower Sixth A" once and every later
      rollover inherits it. Never invented: a clone reproduces the same grades, so
      an identity mapping would place advancing students back in their own grade
      and call it a promotion. A school that has never mapped a ladder gets 0 rows
      and a named blocker on the close scorecard instead.

    Returns dict with counts: terms_created, classrooms_created,
    subject_assignments_created, promotion_rules_created, promotion_mappings_created.
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
        "promotion_mappings_created": 0,
    }

    # The school that owns this rollover. The guard above already refused a
    # cross-school clone, so either year may supply the id; a legacy year with no
    # school of its own falls back to the source row's owner rather than minting
    # an orphan. Every row this function creates is stamped with it, in the
    # get_or_create LOOKUP -- see the Classroom call below for what an unstamped
    # row actually does, and why school does not belong in defaults.
    target_school_id = to_school_id if to_school_id is not None else from_school_id

    def _owner_for(source_row):
        """School id to stamp on a row cloned from ``source_row``."""
        if target_school_id is not None:
            return target_school_id
        return getattr(source_row, "school_id", None)

    with transaction.atomic():
        # Adopt rows a PRE-FIX rollover left in the target year owned by nobody.
        # Until this fix the clone created Terms, Classrooms and
        # SubjectAssignments with school_id NULL, so every tenant that has
        # already rolled over is carrying orphans in to_year. They can only
        # belong to this year's school -- to_year has exactly one owner.
        #
        # Leaving them is not merely cosmetic: the school-scoped lookups below
        # do not match a NULL row, so the clone would try to INSERT alongside
        # one and hit a natural key that is NOT school-scoped -- Term is unique
        # on (academic_year, name) and on (academic_year, position) -- killing
        # the whole rollover with an IntegrityError. updated_at is written
        # explicitly because .update() does not fire auto_now, and an unbumped
        # timestamp would hide the repair from the edge sync cursor.
        if target_school_id is not None:
            adopted_at = timezone.now()
            Term.objects.filter(
                academic_year=to_year, school_id__isnull=True
            ).update(school_id=target_school_id, updated_at=adopted_at)
            Classroom.objects.filter(
                academic_year=to_year, school_id__isnull=True
            ).update(school_id=target_school_id, updated_at=adopted_at)
            SubjectAssignment.objects.filter(
                academic_year=to_year, school_id__isnull=True
            ).update(school_id=target_school_id, updated_at=adopted_at)

        if copy_terms:
            # tenant-isolation-allow: scoped by the school-owned academic_year FK (holds in BOTH tenancy modes, reviewed 2026-09-01)
            # Unlike the old "surrounding tenant context" reason, an FK scope is
            # real on the shared-schema RLS edge too: a Term cannot point at
            # another school's year, so this queryset cannot cross a tenant.
            for t in Term.objects.filter(academic_year=from_year).order_by(
                "position", "start_date"
            ):
                new_term, created = Term.objects.get_or_create(
                    # Term.school is null=True and the clone named no school at
                    # all, so every cloned term was an orphan. school belongs in
                    # the LOOKUP, not in defaults: defaults is only written after
                    # the lookup has already chosen a row, so a school in defaults
                    # re-parents whatever row the unscoped lookup happened to hit.
                    school_id=_owner_for(t),
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

        if copy_classrooms:
            # tenant-isolation-allow: scoped by the school-owned academic_year FK (holds in BOTH tenancy modes, reviewed 2026-09-01)
            for c in Classroom.objects.filter(academic_year=from_year).select_related(
                "department"
            ):
                new_code = f"{c.code}-{suffix}"
                owner_id = _owner_for(c)
                # Is this code already taken FOR THIS SCHOOL, in some OTHER year?
                # Classroom.code is unique per SCHOOL (uniq_classroom_school_code,
                # academics migration 0085), never globally. The old probe asked
                # globally, so it answered a question about OTHER tenants' rows: on
                # the shared-schema RLS edge a stranger holding this code silently
                # pushed THIS school onto the longer fallback code. On the
                # schema-per-tenant cloud the probe only ever saw one tenant, which
                # is why the global form survived review -- its marker was true
                # there and false on the edge, and the edge is the deployment that
                # matters.
                #
                # Rows already in to_year are excluded because they are what THIS
                # clone creates: counting them made a re-run escalate its own
                # output onto the fallback code and clone the year twice. exclude()
                # is safe on academic_year (a non-nullable FK); it would NOT be safe
                # on school, where NOT (school_id = X) is NULL for the orphan rows.
                if (
                    Classroom.objects.filter(school_id=owner_id, code=new_code)
                    .exclude(academic_year=to_year)
                    .exists()
                ):
                    new_code = f"{c.code}-{suffix}-{to_year.id}"
                new_class, created = Classroom.objects.get_or_create(
                    # Classroom.school is null=True and the old call named no school
                    # anywhere, so the rollover minted rows owned by NOBODY. A NULL
                    # school_id matches none of the school-scoped reads the app runs
                    # -- hub counts, the OneRoster export, comms pickers, the
                    # teaching-grid provisioner -- so the rollover reported
                    # "N created" and the school saw none of them. On a forced-RLS
                    # Postgres edge it is worse: the academics policy compares
                    # school_id::text to the session setting, which is NULL rather
                    # than TRUE for a NULL, in WITH CHECK as well as USING, so the
                    # INSERT itself would be refused.
                    school_id=owner_id,
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

        if copy_subject_assignments and old_to_new_term and old_to_new_classroom:
            # tenant-isolation-allow: scoped by the school-owned academic_year FK (holds in BOTH tenancy modes, reviewed 2026-09-01)
            for sa in SubjectAssignment.objects.filter(
                academic_year=from_year
            ).select_related("term", "classroom", "specialty", "subject"):
                new_term = old_to_new_term.get(sa.term_id)
                new_class = old_to_new_classroom.get(sa.classroom_id)
                if not new_term or not new_class:
                    continue
                _, created = SubjectAssignment.objects.get_or_create(
                    # SubjectAssignment.school is null=True: the same orphan hole
                    # as Classroom above, and school goes in the LOOKUP for the
                    # same reason.
                    school_id=_owner_for(sa),
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

        if copy_promotion_mappings and old_to_new_classroom:
            stats["promotion_mappings_created"] = carry_forward_promotion_mappings(
                from_year,
                to_year,
                old_to_new_classroom,
                school_id=target_school_id,
            )

    return stats
