"""Sections lander — persists canonical section / classroom rows into
``apps.academics.Classroom`` (the tenant's class/section model).

Completeness fix (2026-07-11): the old lander wrote only ``name`` (``grade_level``/
``subject_code``/``academic_year`` string were dropped by ``filter_to_model_fields``)
and NEVER set ``Classroom``'s two REQUIRED PROTECT FKs (``academic_year`` +
``department``), so every section quarantined; worse, it upserted on
``Classroom.code`` — which is ``unique=True`` GLOBALLY — using the SOURCE's code
unscoped by school, so on a single-schema deployment a code collision silently
RENAMED another school's classroom. The lander now provisions the required
parents the same safe way ``structure_lander`` does (reuse-by-(school,name),
mint a target-scoped code) and upserts by (school, name) — never the global code.

Canonical row shape::

    {
        "section_code": "MATH-7A",
        "name": "Mathematics Grade 7 Section A",
        "subject_code": "MATH",
        "grade_level": "7",
        "teacher_external_id": "EMP-021",
        "academic_year": "2025-2026"
    }
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterator

from ._helpers import (
    get_or_create_named,
    mint_scoped_code,
    model_field_names,
    persist_dfv_extras,
    record_id_mapping,
    record_row_error,
    row_marks_deletion,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED
from .reason_codes import SOURCE_DELETION


class SectionsLander(Lander):
    domain = "sections"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.academics.models import AcademicYear, Classroom, Department
        except ImportError as exc:
            raise LanderError(
                f"SectionsLander could not import Classroom: {exc!s}"
            ) from exc

        result = LanderResult()
        cls_fields = model_field_names(Classroom)

        for row in canonical_rows:
            # D-3: a source row marked tobedeleted must NOT land as an active
            # Classroom. Classroom has no is_active/status column and enrollments /
            # grades reference it, so we neither import it as active nor hard-delete
            # an existing one — it is held for review with its source row.
            if row_marks_deletion(row):
                record_row_error(
                    result, row,
                    "sections: source marked this class deleted — held for review, "
                    "not imported as active; any existing classroom is left intact "
                    "for referential safety (remove manually if intended).",
                    reason_code=SOURCE_DELETION,
                )
                continue
            code = (row.get("section_code") or row.get("code") or "").strip()
            name = (row.get("name") or code).strip()
            if not code and not name:
                record_row_error(
                    result,
                    row,
                    f"sections: missing section_code/name in {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            if ctx.dry_run:
                exists = self._existing_by_name(Classroom, ctx.school, name) is not None
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue

            try:
                existing = self._existing_by_name(Classroom, ctx.school, name)
                if existing is not None:
                    # Reuse the tenant's own classroom — never rename it.
                    record_id_mapping(ctx=ctx, legacy_id=code or name, canonical_obj=existing, domain="sections")
                    self._persist_section_extras(ctx, existing, row, result)
                    result.skipped += 1
                    continue

                academic_year = self._resolve_academic_year(
                    AcademicYear, ctx.school, (row.get("academic_year") or "").strip(), result
                )
                # The department CODE must be minted from the department this row
                # actually names. Minting every code from the literal "General" gave
                # a "Science" department a GENERAL-derived code, and because the code
                # column is unique the constant hash fallback was exhausted by the
                # 2nd distinct department name, so the 3rd collided and quarantined.
                department_name = (row.get("department") or "General").strip() or "General"
                department, _ = get_or_create_named(
                    model=Department,
                    school=ctx.school,
                    name=department_name,
                    create_kwargs=lambda: {
                        "code": mint_scoped_code(
                            prefix="DPT", name=department_name, school=ctx.school, model=Department
                        )
                    },
                    result=result,
                )

                create_kwargs: dict[str, Any] = {"name": name}
                if "school" in cls_fields and ctx.school is not None:
                    create_kwargs["school"] = ctx.school
                create_kwargs["academic_year"] = academic_year
                create_kwargs["department"] = department
                create_kwargs["code"] = mint_scoped_code(
                    prefix="CLS", name=name or code, school=ctx.school, model=Classroom
                )
                obj = Classroom.objects.create(**create_kwargs)
                result.created += 1
                result.created_ids.append(obj.pk)
                record_id_mapping(ctx=ctx, legacy_id=code or name, canonical_obj=obj, domain="sections")
                self._persist_section_extras(ctx, obj, row, result)
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"sections upsert failed for {code or name}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result

    @staticmethod
    def _existing_by_name(Classroom, school, name):
        qs = Classroom.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
        if "school" in model_field_names(Classroom) and school is not None:
            qs = qs.filter(school=school)
        return qs.filter(name=name).order_by("pk").first()

    @staticmethod
    def _resolve_academic_year(AcademicYear, school, year_name, result):
        """Reuse/create the (school, name) year; fall back to the school's active
        year or a provisioned 'Imported' year so the REQUIRED FK is always set."""
        if year_name:
            year, _ = get_or_create_named(
                model=AcademicYear, school=school, name=year_name,
                create_kwargs=lambda: {
                    "start_date": _dt.date(2000, 1, 1),
                    "end_date": _dt.date(2000, 12, 31),
                    "is_active": False,
                },
                result=result,
            )
            return year
        qs = AcademicYear.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
        if "school" in model_field_names(AcademicYear) and school is not None:
            qs = qs.filter(school=school)
        active = qs.filter(is_active=True).order_by("-start_date").first() or qs.order_by("-start_date").first()
        if active is not None:
            return active
        year, _ = get_or_create_named(
            model=AcademicYear, school=school, name="Imported",
            create_kwargs=lambda: {
                "start_date": _dt.date(2000, 1, 1),
                "end_date": _dt.date(2000, 12, 31),
                "is_active": False,
            },
            result=result,
        )
        return year

    @staticmethod
    def _persist_section_extras(ctx, classroom, row, result):
        persist_dfv_extras(
            ctx=ctx, entity_type="classroom", entity_id=classroom.pk,
            extras={
                "grade_level": (row.get("grade_level") or "").strip(),
                "subject_code": (row.get("subject_code") or "").strip(),
                "source_section_code": (row.get("section_code") or "").strip(),
                "teacher_external_id": (row.get("teacher_external_id") or "").strip(),
            },
            result=result,
        )


register("sections", SectionsLander())
