"""Health lander — persists canonical health rows into ``apps.schoolops.HealthRecord``.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "record_date":         "2025-09-04",   # ISO date
        "category":            "immunization"|"injury"|"medication"|"allergy"|"visit"|"screening",
        "description":         "...",
        "provider":            "School Nurse",
        "confidential":        true,
    }

Upsert key: (student, record_date, category) — re-running a bundle
never duplicates the same health event.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    student_lookup_field,
    truthy,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class HealthLander(Lander):
    domain = "health"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.people.models import StudentProfile
            from apps.schoolops.models import HealthRecord
        except ImportError as exc:
            raise LanderError(
                f"HealthLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        h_fields = model_field_names(HealthRecord)

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            date_val = coerce_date(row.get("record_date") or row.get("date"))
            category = (row.get("category") or row.get("record_type") or "").strip().lower()
            if not external_id or not category:
                result.quarantined += 1
                result.errors.append(
                    f"health: missing student/category in {row!r}"
                )
                continue
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"health: no student with {student_lookup}={external_id!r}"
                )
                continue

            defaults: dict[str, Any] = {
                "record_type": category[:64],
                "notes": (row.get("description") or row.get("notes") or "")[:2000],
                "confidential": truthy(row.get("confidential")),
            }
            if date_val and "recorded_at" in h_fields:
                # recorded_at is typically a DateTimeField; coerce the date.
                import datetime as _dt
                defaults["recorded_at"] = _dt.datetime.combine(date_val, _dt.time.min)
            defaults = filter_to_model_fields(defaults, HealthRecord)

            lookup_kwargs: dict[str, Any] = {"student": student}
            if "record_type" in h_fields and category:
                lookup_kwargs["record_type"] = category[:64]
            if "recorded_at" in h_fields and defaults.get("recorded_at"):
                lookup_kwargs["recorded_at"] = defaults["recorded_at"]

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = HealthRecord.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = HealthRecord.objects.update_or_create(
                    defaults=defaults, **lookup_kwargs,
                )
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx,
                    legacy_id=f"{external_id}:{date_val.isoformat() if date_val else ''}:{category}",
                    canonical_obj=obj, domain="health",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"health upsert failed for {external_id} @ {date_val}/{category}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("health", HealthLander())
