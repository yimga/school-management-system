"""Provision academic structure nodes from country pack + school types."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.academics.academic_structure import AcademicStructureNode
from apps.academics.models import AcademicYear, Classroom, Department
from apps.academics.scheduling import InstructionShift
from apps.governance.academic_pack_bridge import resolve_academic_pack_context


def _slug_code(prefix: str, label: str, idx: int) -> str:
    base = "".join(ch if ch.isalnum() else "-" for ch in label.lower())[:20]
    return f"{prefix}-{base}-{idx}"[:30]


def ensure_general_department(school):
    """Return the single canonical "General" department for ``school``.

    Idempotent and the SOLE creator of the default department. The academic-
    structure provisioner and the Phase-B classroom seeder both need a home
    department; before this they each created their OWN "General" dept with a
    different globally-unique code (``GEN-<id8>`` vs ``<slug>-GEN``), leaving
    every freshly provisioned tenant with two identically-named departments.
    Resolves by canonical code, then adopts any pre-existing same-named
    department (tenants seeded before this fix), else creates one.
    """
    if school is None:
        return None
    canonical_code = f"GEN-{str(school.id)[:8]}"
    dept = Department.objects.filter(school=school, code=canonical_code).first()
    if dept is not None:
        return dept
    # Adopt a legacy "General" department (e.g. the old <slug>-GEN one) rather
    # than minting a duplicate. Oldest wins for determinism.
    dept = (
        Department.objects.filter(school=school, name="General")
        .order_by("id")
        .first()
    )
    if dept is not None:
        return dept
    return Department.objects.create(
        school=school,
        code=canonical_code,
        name="General",
    )


def ensure_general_specialty(school):
    """Return the single canonical "General" specialty for ``school``.

    Idempotent, and the SOLE creator of the default specialty. Nothing in
    provisioning created a Specialty at all, which quietly made a "COMPLETED"
    tenant unusable: ``FeePlan.specialty`` is a non-null FK, so no fee plan could
    be created (the automated fee task just returns ``{"status": "no_plans"}`` as
    SUCCESS), and ``SubjectAssignment.specialty`` is non-null too, so the entire
    teaching grid was unbuildable — a day-1 teacher opened the classroom dropdown
    and saw nothing, with no error to explain why.

    ``Specialty.code`` is GLOBALLY unique (max_length=30), NOT unique-per-school,
    so the code MUST be namespaced by school id — exactly the trap documented on
    ``Classroom.code`` below, where two schools sharing a pack school_type
    collided and the SECOND school's provisioning died on a UNIQUE violation.
    Mirrors ``ensure_general_department``: resolve by canonical code, adopt any
    pre-existing same-named row, else create.
    """
    if school is None:
        return None
    from apps.academics.models import Specialty

    canonical_code = f"SPEC-GEN-{str(school.id)[:8]}"[:30]
    specialty = Specialty.objects.filter(school=school, code=canonical_code).first()
    if specialty is not None:
        return specialty
    specialty = (
        Specialty.objects.filter(school=school, name="General").order_by("id").first()
    )
    if specialty is not None:
        return specialty
    return Specialty.objects.create(
        school=school,
        department=ensure_general_department(school),
        code=canonical_code,
        name="General",
    )


def provision_teaching_grid_for_school(
    school,
    *,
    academic_year: AcademicYear | None = None,
) -> dict[str, Any]:
    """Seed the classroom x subject x term grid a school actually teaches from.

    THE GAP THIS CLOSES
    -------------------
    Provisioning marked a tenant COMPLETED while creating ZERO SubjectAssignments,
    and that model is the hinge the whole school day turns on: teachers reach
    classrooms through ``TeacherAssignment -> subject_assignment__classroom``, and
    marks point at a SubjectAssignment. With none, a school that provisioned
    "successfully" could not take attendance or enter a single grade — and nothing
    raised. Every surface just rendered an empty dropdown, which reads as "no data
    yet" rather than "your tenant is broken".

    Idempotent (get_or_create on the model's own unique_together) so a resume
    completes a partial grid instead of duplicating it. Honours the third-term
    rule that ``SubjectAssignment.clean()`` enforces — ``.create()`` never calls
    ``clean()``, so a blind seed would write rows the model itself considers
    invalid.
    """
    if school is None:
        return {"created_assignments": 0, "skipped": "no_school"}

    from apps.academics.models import Classroom, Subject, SubjectAssignment, Term

    year = academic_year
    if year is None:
        year = AcademicYear.objects.filter(school=school, is_active=True).first()
    if year is None:
        year = AcademicYear.objects.filter(school=school).order_by("-start_date").first()
    if year is None:
        return {"created_assignments": 0, "skipped": "no_academic_year"}

    classrooms = list(Classroom.objects.filter(school=school, academic_year=year))
    subjects = list(Subject.objects.filter(school=school))
    terms = list(Term.objects.filter(school=school, academic_year=year).order_by("position"))
    if not (classrooms and subjects and terms):
        return {
            "created_assignments": 0,
            "skipped": "missing_prerequisites",
            "classrooms": len(classrooms),
            "subjects": len(subjects),
            "terms": len(terms),
        }

    specialty = ensure_general_specialty(school)
    if specialty is None:
        return {"created_assignments": 0, "skipped": "no_specialty"}

    created = 0
    skipped_third_term = 0
    with transaction.atomic():
        for classroom in classrooms:
            for term in terms:
                # SubjectAssignment.clean() rejects a third-term row on a
                # classroom that disallows it. create() does not call clean(), so
                # respect the rule here rather than seeding invalid rows.
                if term.position == 3 and not classroom.allows_third_term:
                    skipped_third_term += len(subjects)
                    continue
                for subject in subjects:
                    _, was_created = SubjectAssignment.objects.get_or_create(
                        academic_year=year,
                        term=term,
                        classroom=classroom,
                        specialty=specialty,
                        subject=subject,
                        defaults={"school": school},
                    )
                    if was_created:
                        created += 1

    return {
        "created_assignments": created,
        "classrooms": len(classrooms),
        "subjects": len(subjects),
        "terms": len(terms),
        "specialty_code": getattr(specialty, "code", ""),
        "skipped_third_term": skipped_third_term,
        "total_assignments": SubjectAssignment.objects.filter(
            school=school, academic_year=year
        ).count(),
    }


def provision_academic_structure_for_school(
    school,
    *,
    school_type_codes: list[str] | None = None,
    academic_year: AcademicYear | None = None,
) -> dict[str, Any]:
    """
    Build cycle nodes from localization pack school_types and optional level leaves.

    Idempotent per (school, school_type code): reuses existing cycle nodes by metadata.
    """
    if school is None:
        return {"created_nodes": 0, "created_classrooms": 0}

    iso = (getattr(school, "country_code", None) or "")[:2].upper()
    ctx = resolve_academic_pack_context(iso)
    pack = ctx.get("country_pack") or {}
    types = pack.get("school_types") or []
    selected = {c.strip().lower() for c in (school_type_codes or []) if c}
    if selected:
        types = [t for t in types if str(t.get("code", "")).lower() in selected]

    year = academic_year
    if year is None:
        year = (
            AcademicYear.objects.filter(school=school).order_by("-start_date").first()
        )
    if year is None:
        return {"created_nodes": 0, "created_classrooms": 0, "skipped": "no_academic_year"}

    dept = ensure_general_department(school)

    created_nodes = 0
    created_classrooms = 0

    with transaction.atomic():
        for idx, st in enumerate(types):
            code = str(st.get("code") or f"type-{idx}")
            label = str(st.get("label") or code)
            cycle = AcademicStructureNode.objects.filter(
                school=school,
                node_type=AcademicStructureNode.NodeType.CYCLE,
                structural_metadata__pack_school_type=code,
            ).first()
            if cycle is None:
                cycle = AcademicStructureNode.objects.create(
                    school=school,
                    parent=None,
                    node_type=AcademicStructureNode.NodeType.CYCLE,
                    local_label=label,
                    sort_order=idx * 10,
                    structural_metadata={
                        "pack_school_type": code,
                        "primary_sector": st.get("primary_sector"),
                    },
                )
                created_nodes += 1

            if st.get("primary_sector") in ("secondary", "middle", "k12"):
                class_label = f"{label} — Group A"
                # Classroom.code is GLOBALLY unique (max_length=30), so the seed
                # code MUST be namespaced by school id — otherwise two schools
                # sharing a pack school_type (e.g. two US "high" schools) generate
                # the same code and the SECOND school's provisioning dies with a
                # UNIQUE collision (the "provisioning fails for the next school"
                # bug). Mirrors the school-scoped dept_code above.
                sid = str(getattr(school, "id", "")).replace("-", "")[:8]
                room_code = _slug_code(f"{sid}-{code}", label, 0)
                classroom = Classroom.objects.filter(
                    school=school, academic_year=year, code=room_code
                ).first()
                if classroom is None:
                    classroom = Classroom.objects.create(
                        school=school,
                        academic_year=year,
                        department=dept,
                        name=class_label,
                        code=room_code,
                    )
                    created_classrooms += 1
                leaf = AcademicStructureNode.objects.filter(
                    school=school,
                    classroom=classroom,
                ).first()
                if leaf is None:
                    AcademicStructureNode.objects.create(
                        school=school,
                        parent=cycle,
                        node_type=AcademicStructureNode.NodeType.CLASSROOM_LEAF,
                        local_label=class_label,
                        sort_order=0,
                        structural_metadata={"pack_school_type": code},
                        classroom=classroom,
                    )
                    created_nodes += 1

    shifts_created = _ensure_default_instruction_shifts(school, iso)

    return {
        "created_nodes": created_nodes,
        "created_classrooms": created_classrooms,
        "school_types_processed": len(types),
        "shifts_created": shifts_created,
    }


def _ensure_default_instruction_shifts(school, country_code: str) -> int:
    """Seed morning/afternoon shifts when the country pack supports multi-shift."""
    ctx = resolve_academic_pack_context(country_code)
    if not ctx.get("supports_multi_shift"):
        return 0
    created = 0
    for code, label, order in (
        ("morning", "Morning (matinée)", 0),
        ("afternoon", "Afternoon (vespertina)", 10),
    ):
        _, was_created = InstructionShift.objects.get_or_create(
            school=school,
            code=code,
            defaults={"label": label, "sort_order": order},
        )
        if was_created:
            created += 1
    return created
