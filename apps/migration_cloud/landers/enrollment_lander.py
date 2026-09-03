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
    conflict_resolution_for,
    detect_conflict,
    filter_to_model_fields,
    map_enrollment_status,
    model_field_names,
    normalize_canonical_row,
    persist_dfv_extras,
    record_row_error,
    resolve_student,
    row_savepoint,
    save_scoped,
    student_lookup_field,
    student_name_from_row,
    unresolved_student_reason,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import INVALID_REF, LANDER_ERROR, MISSING_REQUIRED


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
            row = normalize_canonical_row("enrollment", row, ctx)
            external_id = (
                row.get("student_external_id") or row.get("external_id") or ""
            ).strip()
            if not (external_id or student_name_from_row(row)):
                record_row_error(
                    result,
                    row,
                    f"enrollment: missing student_external_id in {row!r}",
                    reason_code=MISSING_REQUIRED, field="student_external_id",
                )
                continue
            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
                row=row,
            )
            if student is None:
                record_row_error(
                    result,
                    row,
                    unresolved_student_reason(
                        domain="enrollment",
                        ctx=ctx,
                        student_model=StudentProfile,
                        row=row,
                        external_id=external_id,
                        lookup_field=student_lookup,
                    ),
                    reason_code=INVALID_REF,
                )
                continue

            section_ref = (row.get("section_code") or row.get("section") or "").strip()
            year_ref = (row.get("academic_year") or "").strip()
            # enrollment_status is a lifecycle token → StudentProfile.status (a
            # constrained choice), NOT a phantom ``enrollment_status`` column.
            updates: dict[str, Any] = {
                "status": map_enrollment_status(row.get("enrollment_status")),
                "joined_date": coerce_date(
                    row.get("enrolled_at") or row.get("enrollment_date")
                ),
                "section": section_ref,
            }
            updates = filter_to_model_fields(updates, StudentProfile)
            # grade_level + the raw enrollment token aren't first-class columns —
            # preserve them as custom fields so nothing is silently dropped.
            extras = {
                "grade_level": (row.get("grade_level") or "").strip(),
                "enrollment_status": (row.get("enrollment_status") or "").strip(),
            }
            extras = {k: v for k, v in extras.items() if k not in student_fields and v}

            # Placement: resolve NAMED structures into real FKs at the
            # student's school. The docstring's "linked to a Section if
            # present" was never implemented — and a canonical academic_year
            # string assigned onto the FK column raised ValueError, so any
            # bundle carrying that column quarantined every enrollment row.
            # An unresolvable reference quarantines VISIBLY (create the
            # structure at the target, then re-drive) — it never lands a
            # half-placed student silently.
            school = getattr(ctx, "school", None) or getattr(student, "school", None)
            unresolved: list[str] = []
            if section_ref and "classroom" in student_fields:
                classroom = _resolve_classroom(school, section_ref)
                if classroom is None:
                    from apps.migration_cloud.landers.student_lander import (
                        _resolve_or_create_classroom,
                    )

                    classroom = _resolve_or_create_classroom(school, section_ref, student)
                if classroom is not None:
                    updates["classroom"] = classroom
                    if "academic_year" in student_fields and not year_ref:
                        year = getattr(classroom, "academic_year", None)
                        if year is not None:
                            updates["academic_year"] = year
                else:
                    unresolved.append(f"section {section_ref!r}")
            if year_ref and "academic_year" in student_fields:
                year = _resolve_academic_year(school, year_ref)
                if year is not None:
                    updates["academic_year"] = year
                else:
                    unresolved.append(f"academic year {year_ref!r}")
            specialty_ref = (row.get("specialty") or "").strip()
            if specialty_ref and "specialty" in student_fields:
                specialty = _resolve_specialty(school, specialty_ref)
                if specialty is None:
                    from apps.migration_cloud.landers.student_lander import (
                        _resolve_specialty_fuzzy,
                    )

                    specialty = _resolve_specialty_fuzzy(school, specialty_ref)
                if specialty is not None:
                    updates["specialty"] = specialty
                else:
                    unresolved.append(f"specialty {specialty_ref!r}")
            if unresolved:
                record_row_error(
                    result,
                    row,
                    f"enrollment: could not resolve {', '.join(unresolved)} at the "
                    f"school for student {external_id!r}",
                    reason_code=INVALID_REF,
                )
                continue
            if not updates and not extras:
                continue

            if ctx.dry_run:
                result.updated += 1
                continue
            try:
                old_snapshot: dict = {}
                if updates:
                    # Log any existing-vs-incoming diff for operator review and
                    # honour a prior PRESERVE decision. The other person landers
                    # route existing-row writes through detect_conflict /
                    # conflict_resolution_for; enrollment previously did a bare
                    # setattr, silently overwriting a student's lifecycle state
                    # (grade/status/section) with no conflict row and an EMPTY
                    # `old` -- so the field-level apply audit under-reported the
                    # very overwrites that touch pre-existing student records.
                    detect_conflict(
                        ctx=ctx, domain="enrollment", canonical_obj=student,
                        incoming=updates, legacy_id=external_id,
                    )
                    if conflict_resolution_for(ctx=ctx, canonical_obj=student) == "PRESERVE":
                        # Operator kept the existing enrollment; skip the field
                        # writes. DFV extras below are additive, not an overwrite,
                        # so they still land.
                        persist_dfv_extras(
                            ctx=ctx, entity_type="student", entity_id=student.pk,
                            extras=extras, result=result,
                        )
                        result.skipped += 1
                        continue
                    # Snapshot the OLD non-empty values BEFORE overwriting so the
                    # field-level apply audit records which fields this bundle
                    # overwrote (it reads entry["old"].keys()). Empty -> value is
                    # a fill-in, not an overwrite, so it is not recorded.
                    for k in updates:
                        cur = getattr(student, k, None)
                        if cur not in (None, ""):
                            old_snapshot[k] = (
                                cur if isinstance(cur, (str, int, float, bool))
                                else str(cur)[:200]
                            )
                    for k, v in updates.items():
                        setattr(student, k, v)
                    # Per-row savepoint: enrollment lands in the same forced-atomic
                    # finance transaction, so a bad row must roll back only itself.
                    #
                    # save_scoped, not a bare update_fields: placing a pupil sets the
                    # third of academic_year/specialty/classroom, which makes the model
                    # mint an admission_number and rebuild search_index INSIDE save() --
                    # neither of which is in updates, so both were computed and dropped.
                    with row_savepoint():
                        save_scoped(student, list(updates.keys()))
                persist_dfv_extras(
                    ctx=ctx, entity_type="student", entity_id=student.pk,
                    extras=extras, result=result,
                )
                result.updated += 1
                result.updated_ids_with_old_values.append(
                    {"pk": student.pk, "old": old_snapshot}
                )
                from ._helpers import record_id_mapping
                record_id_mapping(
                    ctx=ctx, legacy_id=external_id, canonical_obj=student, domain="enrollment",
                )
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"enrollment update failed for {external_id}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


def _resolve_classroom(school, ref: str):
    """Classroom at the given school whose code (exact) or name matches ``ref``."""
    try:
        from apps.academics.models import Classroom
    except ImportError:
        return None
    if school is not None:
        qs = Classroom.objects.filter(school=school)
    else:
        qs = Classroom.objects.all()  # tenant-isolation-allow: schema-per-tenant-context-isolates-when-no-school-fk
    return (
        qs.filter(code=ref).order_by("-pk").first()  # tenant-isolation-allow: scoped-above-via-school-filter-or-schema-context
        or qs.filter(name=ref).order_by("-pk").first()  # tenant-isolation-allow: scoped-above-via-school-filter-or-schema-context
    )


def _resolve_specialty(school, ref: str):
    """Specialty at the given school whose code (exact) or name matches ``ref``."""
    try:
        from apps.academics.models import Specialty
    except ImportError:
        return None
    if school is not None:
        qs = Specialty.objects.filter(school=school)
    else:
        qs = Specialty.objects.all()  # tenant-isolation-allow: schema-per-tenant-context-isolates-when-no-school-fk
    return (
        qs.filter(code=ref).order_by("-pk").first()  # tenant-isolation-allow: scoped-above-via-school-filter-or-schema-context
        or qs.filter(name=ref).order_by("-pk").first()  # tenant-isolation-allow: scoped-above-via-school-filter-or-schema-context
    )


def _resolve_academic_year(school, name: str):
    try:
        from apps.academics.models import AcademicYear
    except ImportError:
        return None
    if school is not None:
        qs = AcademicYear.objects.filter(school=school)
    else:
        qs = AcademicYear.objects.all()  # tenant-isolation-allow: schema-per-tenant-context-isolates-when-no-school-fk
    return qs.filter(name=name).order_by("-pk").first()  # tenant-isolation-allow: scoped-above-via-school-filter-or-schema-context


register("enrollment", EnrollmentLander())
