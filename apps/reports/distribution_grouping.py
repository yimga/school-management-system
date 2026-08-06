"""How a school groups report cards for bulk print / share.

A general-education school thinks in **classes** ("Form 4A"): a term's cards are
printed and handed out class by class. A technical college or a STEM academy
thinks in **specialties / streams** ("Electrical Engineering", "Robotics"): the
same cohort is organised by track, and a class label means little. Bulk print
and bulk share must follow whichever axis the school actually uses, or the
"print this group's cards" verb hands a technical college the wrong stack of
paper.

This module is the single place that answers two questions the bulk-print,
bulk-generate and bulk-share paths all need to agree on:

1. ``resolve_report_group_mode(school)`` — CLASS or SPECIALTY, from the config
   cascade first (an explicit ``report_card_group_mode`` override always wins)
   and the school's ``school_type`` otherwise. No hardcoded per-school
   branching — the default is derived, the override is honoured.
2. ``scoped_student_queryset(...)`` — the ONE definition of "the students in this
   run". ``bulk_generation`` builds on it too, so a card that is generated,
   printed and shared is always the same set of students; a second copy of the
   ``school__isnull=True`` scoping rule is exactly how the three paths drift.
"""
from __future__ import annotations

from django.db.models import Q

# Group axes. Stable string values — persisted on ``ReportCardBatch`` and read
# back by the applier, so they are a contract, not a display detail.
GROUP_MODE_CLASS = "CLASS"
GROUP_MODE_SPECIALTY = "SPECIALTY"
VALID_GROUP_MODES = (GROUP_MODE_CLASS, GROUP_MODE_SPECIALTY)

# Config key a school (or a blueprint) can set to force an axis regardless of
# type — e.g. a technical college that still hands out cards class by class.
GROUP_MODE_CONFIG_KEY = "report_card_group_mode"

# School types whose cards are organised by specialty/stream, not class. These
# are the values the platform stamps on ``School.school_type`` from the module
# manifest (documented on the field itself); a type not listed here defaults to
# class grouping, which is what a base school wants.
_SPECIALTY_SCHOOL_TYPES = frozenset({"TECHNICAL_COLLEGE", "STEM_ACADEMY"})


def resolve_report_group_mode(school) -> str:
    """Return CLASS or SPECIALTY for ``school`` (cascade first, type-derived else).

    Fail-soft: an unknown/absent school, a broken resolver, or a garbage
    override all fall back to CLASS — the axis every school understands.
    """
    # 1. Explicit config override wins (7-layer cascade, not a hardcode).
    try:
        from apps.platform_runtime.config_resolver import get_effective_config

        override = get_effective_config(school, GROUP_MODE_CONFIG_KEY, default=None)
    except Exception:  # noqa: BLE001 — config resolver is fail-soft by contract
        override = None
    if isinstance(override, str) and override.strip().upper() in VALID_GROUP_MODES:
        return override.strip().upper()

    # 2. Derive from the school's type.
    school_type = str(getattr(school, "school_type", "") or "").strip().upper()
    if school_type in _SPECIALTY_SCHOOL_TYPES:
        return GROUP_MODE_SPECIALTY
    return GROUP_MODE_CLASS


def scoped_student_queryset(school, academic_year, *, classroom=None, specialty=None):
    """The students a bulk run covers — the single scoping definition.

    Mirrors the intent of ``bulk_generation``: bind to the tenant + academic
    year (the schema already isolates the tenant, and the per-row ``school`` FK
    is very often NULL on seeded data, so ``school__isnull=True`` must be
    included or a bare ``school=`` drops almost the whole roll), then narrow to
    one classroom or one specialty when asked.
    """
    from apps.people.models import StudentProfile

    students = StudentProfile.objects.filter(  # tenant-isolation-allow: bulk-report-scoped-via-caller-school-and-academic-year
        academic_year=academic_year, is_active=True
    )
    if school is not None:
        students = students.filter(Q(school=school) | Q(school__isnull=True))
    if classroom is not None:
        students = students.filter(classroom=classroom)
    if specialty is not None:
        students = students.filter(specialty=specialty)
    return students.select_related("classroom", "specialty", "school").order_by(
        "last_name", "first_name"
    )


def _group_scope_kwargs(mode: str, ref_obj) -> dict:
    """Translate a group axis + ref object into ``scoped_student_queryset`` kwargs."""
    if mode == GROUP_MODE_SPECIALTY:
        return {"specialty": ref_obj}
    return {"classroom": ref_obj}


def list_report_groups(school, academic_year) -> list[dict]:
    """Enumerate the bulk-print/share groups for a school's active axis.

    Returns one dict per group with a stable ``ref_kind``/``ref_id`` the views
    round-trip, a human ``label``/``code``, and a live ``student_count`` so the
    console can show "Form 4A — 32 students" without a second query per row.
    Groups with zero active students are still listed (a school needs to see an
    empty class exists), sorted by label.
    """
    from apps.academics.models import Classroom, Specialty

    mode = resolve_report_group_mode(school)
    groups: list[dict] = []

    if mode == GROUP_MODE_SPECIALTY:
        specialties = Specialty.objects.filter(  # tenant-isolation-allow: specialty-scoped-via-caller-school-or-shared-catalog
            Q(school=school) | Q(school__isnull=True)
        ).order_by("name")
        for spec in specialties:
            count = scoped_student_queryset(
                school, academic_year, specialty=spec
            ).count()
            groups.append(
                {
                    "mode": mode,
                    "ref_kind": "specialty",
                    "ref_id": spec.pk,
                    "label": spec.name,
                    "code": spec.code,
                    "student_count": count,
                }
            )
    else:
        classrooms = Classroom.objects.filter(  # tenant-isolation-allow: classroom-scoped-via-caller-school-and-academic-year
            Q(school=school) | Q(school__isnull=True),
            academic_year=academic_year,
        ).order_by("name")
        for room in classrooms:
            count = scoped_student_queryset(
                school, academic_year, classroom=room
            ).count()
            groups.append(
                {
                    "mode": mode,
                    "ref_kind": "classroom",
                    "ref_id": room.pk,
                    "label": room.name,
                    "code": room.code,
                    "student_count": count,
                }
            )

    groups.sort(key=lambda g: (g["label"] or "").lower())
    return groups


def resolve_group(school, academic_year, mode: str, ref_id):
    """Resolve a (mode, ref_id) pair to its ref object + scoping kwargs.

    Returns ``(ref_obj, scope_kwargs, label)`` or ``(None, None, "")`` when the
    ref cannot be resolved for this school (a stale/foreign id must not silently
    fall through to "the whole year").
    """
    from apps.academics.models import Classroom, Specialty

    mode = (mode or "").strip().upper()
    if mode not in VALID_GROUP_MODES:
        mode = resolve_report_group_mode(school)

    try:
        ref_id_int = int(ref_id)
    except (TypeError, ValueError):
        return None, None, ""

    if mode == GROUP_MODE_SPECIALTY:
        ref_obj = (
            Specialty.objects.filter(  # tenant-isolation-allow: specialty-scoped-via-caller-school-or-shared-catalog
                Q(school=school) | Q(school__isnull=True), pk=ref_id_int
            ).first()
        )
    else:
        ref_obj = (
            Classroom.objects.filter(  # tenant-isolation-allow: classroom-scoped-via-caller-school-and-academic-year
                Q(school=school) | Q(school__isnull=True),
                pk=ref_id_int,
                academic_year=academic_year,
            ).first()
        )
    if ref_obj is None:
        return None, None, ""
    return ref_obj, _group_scope_kwargs(mode, ref_obj), getattr(ref_obj, "name", "")
