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

    dept_code = f"GEN-{str(school.id)[:8]}"
    dept = Department.objects.filter(school=school, code=dept_code).first()
    if dept is None:
        dept = Department.objects.create(
            school=school,
            code=dept_code,
            name="General",
        )

    created_nodes = 0
    created_classrooms = 0

    with transaction.atomic():
        for idx, st in enumerate(types):
            code = str(st.get("code") or f"type-{idx}")
            label = str(st.get("label") or code)
            meta_key = f"pack_school_type:{code}"
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
                room_code = _slug_code(code, label, 0)
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
