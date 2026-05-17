"""Attendance lander — persists canonical attendance rows into `apps.academics.Attendance`.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "date": "2025-09-04",         # ISO date (transformed via date_iso_normalize)
        "status": "present"|"absent"|"late"|"excused"|"holiday"|"suspended",
        "section_code": "MATH-7A",    # optional; linked to a Section if present
        "remarks": "..."
    }

Upsert key: (student, date) — re-running a bundle never duplicates attendance.
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


_STATUS_MAP = {
    "present": "P",
    "absent": "A",
    "late": "L",
    "excused": "E",
    "holiday": "H",
    "suspended": "S",
}


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

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            date_val = coerce_date(row.get("date"))
            status_raw = (row.get("status") or "").strip().lower()
            if not external_id or date_val is None or not status_raw:
                result.quarantined += 1
                result.errors.append(
                    f"attendance: missing student/date/status in {row!r}"
                )
                continue
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"attendance: no student with {student_lookup}={external_id!r}"
                )
                continue

            mapped_status = _STATUS_MAP.get(status_raw, status_raw.upper()[:1] or "A")
            defaults: dict[str, Any] = {"date": date_val}
            if status_field:
                defaults["status"] = mapped_status
            if "remarks" in att_fields and row.get("remarks"):
                defaults["remarks"] = str(row["remarks"])[:255]

            defaults = filter_to_model_fields(defaults, Attendance)

            if ctx.dry_run:
                exists = Attendance.objects.filter(student=student, date=date_val).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = Attendance.objects.update_or_create(
                    student=student, date=date_val, defaults=defaults,
                )
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                from ._helpers import record_id_mapping
                record_id_mapping(
                    ctx=ctx, legacy_id=f"{external_id}:{date_val.isoformat()}",
                    canonical_obj=obj, domain="attendance",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"attendance upsert failed for {external_id} @ {date_val}: {type(exc).__name__}: {exc}"
                )
        return result


register("attendance", AttendanceLander())
