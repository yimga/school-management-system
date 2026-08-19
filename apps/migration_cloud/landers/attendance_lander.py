"""Attendance lander — persists canonical attendance rows into `apps.academics.Attendance`.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "date": "2025-09-04",         # ISO date (transformed via date_iso_normalize)
        "status": "present"|"absent"|"late"|"excused"|"holiday"|"suspended",
        "section_code": "MATH-7A",    # optional; linked to a Section if present
        "remarks": "..."
    }

Upsert key: (student, classroom, date) — mirrors the model's unique constraint,
so per-period rows for different classes land distinctly and re-running a bundle
never duplicates attendance. classroom is resolved from the row's section_code
(school-scoped) or the student's current classroom.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    unresolved_student_reason,
    student_name_from_row,
    coerce_date,
    filter_to_model_fields,
    map_attendance_status,
    model_field_names,
    resolve_student,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


def _resolve_row_classroom(row, student, ctx, att_fields):
    """Resolve the Classroom for an attendance row (part of the unique key).

    Prefer an EXISTING classroom named by the row's ``section_code`` — scoped to
    this school so a source code can't resolve another tenant's classroom — so
    genuine per-section / per-period rows land distinctly. Fall back to the
    student's current classroom. Never provisions a new classroom. Returns None
    when neither is available (the upsert then keys on ``(student, date)`` only).
    """
    if "classroom" not in att_fields:
        return None
    section_code = (row.get("section_code") or row.get("classroom_code") or "").strip()
    if section_code:
        try:
            from apps.academics.models import Classroom
            cfields = model_field_names(Classroom)
            qs = Classroom.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
            if "school" in cfields and ctx.school is not None:
                qs = qs.filter(school=ctx.school)
            cls = None
            if "code" in cfields:
                cls = qs.filter(code=section_code).first()
            if cls is None and "name" in cfields:
                cls = qs.filter(name=section_code).first()
            if cls is not None:
                return cls
        except Exception:  # noqa: BLE001 — classroom resolution is best-effort
            pass
    if getattr(student, "classroom_id", None):
        return student.classroom
    return None


class AttendanceLander(Lander):
    domain = "attendance"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.academics.models import Attendance
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"AttendanceLander could not import Attendance / StudentProfile: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        att_fields = model_field_names(Attendance)
        status_field = "status" if "status" in att_fields else None
        # Valid Status choices + the model default, read off the model so a schema
        # change can't silently reintroduce out-of-choice values.
        status_choices = {c for c, _ in getattr(Attendance, "Status").choices}
        status_default = getattr(
            Attendance._meta.get_field("status"), "default", "present"
        )
        if not isinstance(status_default, str):
            status_default = "present"

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            date_val = coerce_date(row.get("date"))
            status_raw = (row.get("status") or "").strip().lower()
            if not (external_id or student_name_from_row(row)) or date_val is None or not status_raw:
                result.quarantined += 1
                result.errors.append(
                    f"attendance: missing student/date/status in {row!r}"
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
                result.quarantined += 1
                result.errors.append(
                    unresolved_student_reason(
                        domain="attendance",
                        ctx=ctx,
                        student_model=StudentProfile,
                        row=row,
                        external_id=external_id,
                        lookup_field=student_lookup,
                    )
                )
                continue

            mapped_status = map_attendance_status(
                status_raw, valid=status_choices, default=status_default
            )
            # Resolve the classroom for this row. The model's unique key is
            # (student, classroom, date), so the upsert MUST key on classroom too —
            # keying only on (student, date) collapses genuinely-distinct per-period
            # rows (last-wins) and raises MultipleObjectsReturned when >1 classroom
            # already exists for a (student, date).
            # See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (C-3).
            row_classroom = _resolve_row_classroom(row, student, ctx, att_fields)

            defaults: dict[str, Any] = {"date": date_val}
            if status_field:
                defaults["status"] = mapped_status
            # Canonical attendance carries the remark under ``notes``; the model
            # column is ``remarks``. Read notes first, fall back to remarks.
            remark = (row.get("notes") or row.get("remarks") or "").strip()
            if "remarks" in att_fields and remark:
                defaults["remarks"] = remark[:255]
            # Bind the row to the bundle's school (NOT NULL FK on single-schema).
            if "school" in att_fields and ctx.school is not None:
                defaults["school"] = ctx.school

            defaults = filter_to_model_fields(defaults, Attendance)

            # Upsert key mirrors the model's unique constraint (student, classroom,
            # date). classroom is added only when resolved — a NULL classroom keeps
            # the historic (student, date) behaviour rather than risking a NOT NULL
            # create failure.
            lookup: dict[str, Any] = {"student": student, "date": date_val}
            legacy_key = f"{external_id}:{date_val.isoformat()}"
            if "classroom" in att_fields and row_classroom is not None:
                lookup["classroom"] = row_classroom
                legacy_key = f"{legacy_key}:{row_classroom.pk}"

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            if ctx.dry_run:
                exists = Attendance.objects.filter(**lookup).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import (
                    record_id_mapping,
                    upsert_with_conflict_detection,
                )
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="attendance", model=Attendance,
                    lookup=lookup, defaults=defaults,
                    legacy_id=legacy_key,
                )
                if preserved:
                    # Operator resolved this attendance conflict as PRESERVE.
                    result.skipped += 1
                    record_id_mapping(
                        ctx=ctx, legacy_id=legacy_key,
                        canonical_obj=obj, domain="attendance",
                    )
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx, legacy_id=legacy_key,
                    canonical_obj=obj, domain="attendance",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"attendance upsert failed for {external_id} @ {date_val}: {type(exc).__name__}: {exc}"
                )
        return result


register("attendance", AttendanceLander())
