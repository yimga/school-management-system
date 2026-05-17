"""Sections lander — persists canonical section / classroom rows into
``apps.academics.Classroom`` (the tenant's class/section model).

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

from typing import Any, Iterator

from ._helpers import filter_to_model_fields, model_field_names
from .base import Lander, LanderContext, LanderError, LanderResult, register


class SectionsLander(Lander):
    domain = "sections"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.academics.models import Classroom
        except ImportError as exc:
            raise LanderError(
                f"SectionsLander could not import Classroom: {exc!s}"
            ) from exc

        result = LanderResult()
        cls_fields = model_field_names(Classroom)
        code_field = "code" if "code" in cls_fields else ("slug" if "slug" in cls_fields else None)
        if code_field is None:
            raise LanderError("SectionsLander: Classroom model has no code/slug field for upsert.")

        for row in canonical_rows:
            code = (row.get("section_code") or row.get("code") or "").strip()
            if not code:
                result.quarantined += 1
                result.errors.append(f"sections: missing section_code in {row!r}")
                continue

            defaults: dict[str, Any] = {
                "name": (row.get("name") or code),
                "grade_level": (row.get("grade_level") or "").strip(),
                "subject_code": (row.get("subject_code") or "").strip(),
                "academic_year": (row.get("academic_year") or "").strip(),
            }
            defaults = filter_to_model_fields(defaults, Classroom)

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                exists = Classroom.objects.filter(**{code_field: code}).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = Classroom.objects.update_or_create(
                    **{code_field: code}, defaults=defaults,
                )
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                from ._helpers import record_id_mapping
                record_id_mapping(ctx=ctx, legacy_id=code, canonical_obj=obj, domain="sections")
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"sections upsert failed for {code}: {type(exc).__name__}: {exc}"
                )
        return result


register("sections", SectionsLander())
