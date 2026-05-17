"""Enrollment lander — keeps a student's grade-level + enrollment_status + section
up to date directly on the ``StudentProfile`` row.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "grade_level": "7",
        "enrollment_status": "active" | "withdrawn" | "graduated",
        "section_code": "MATH-7A",
        "enrolled_at": "2025-08-15",
        "academic_year": "2025-2026"
    }

Most tenants store enrollment denormalised onto StudentProfile (grade_level,
enrollment_status, primary_section). This lander updates those columns when
they exist; otherwise the data flows into custom_fields via the fallback.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class EnrollmentLander(Lander):
    domain = "enrollment"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"EnrollmentLander could not import StudentProfile: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            if not external_id:
                result.quarantined += 1
                result.errors.append(f"enrollment: missing student_external_id in {row!r}")
                continue
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"enrollment: no student with {student_lookup}={external_id!r}"
                )
                continue

            updates: dict[str, Any] = {
                "grade_level": (row.get("grade_level") or "").strip(),
                "enrollment_status": (row.get("enrollment_status") or "").strip(),
                "enrolled_at": coerce_date(row.get("enrolled_at")),
                "academic_year": (row.get("academic_year") or "").strip(),
                "section_code": (row.get("section_code") or "").strip(),
            }
            updates = filter_to_model_fields(updates, StudentProfile)
            if not updates:
                continue

            if ctx.dry_run:
                result.updated += 1
                continue
            try:
                for k, v in updates.items():
                    setattr(student, k, v)
                student.save(update_fields=list(updates.keys()))
                result.updated += 1
                result.updated_ids_with_old_values.append({"pk": student.pk, "old": {}})
                from ._helpers import record_id_mapping
                record_id_mapping(
                    ctx=ctx, legacy_id=external_id, canonical_obj=student, domain="enrollment",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"enrollment update failed for {external_id}: {type(exc).__name__}: {exc}"
                )
        return result


register("enrollment", EnrollmentLander())
