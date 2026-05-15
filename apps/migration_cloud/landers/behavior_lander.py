"""Behavior lander — persists canonical behavior incidents into
``apps.academics.Incident`` (the tenant's incident model).

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "date": "2025-09-04",
        "type": "tardy" | "fight" | "kudos" | "other",
        "severity": "low" | "med" | "high",
        "description": "...",
        "action_taken": "...",
        "reporter_external_id": "EMP-021"
    }

Upsert key: (student, date, type, description-hash) when those fields exist.
Defensive: never aborts the bundle on one bad row.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class BehaviorLander(Lander):
    domain = "behavior"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.academics.models import Incident
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"BehaviorLander could not import Incident / StudentProfile: {exc!s}"
            ) from exc

        result = LanderResult()
        incident_fields = model_field_names(Incident)
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            date_val = coerce_date(row.get("date"))
            description = (row.get("description") or "").strip()
            if not external_id or date_val is None or not description:
                result.quarantined += 1
                result.errors.append(
                    f"behavior: missing student/date/description in {row!r}"
                )
                continue
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"behavior: no student with {student_lookup}={external_id!r}"
                )
                continue

            stable_hash = hashlib.sha1(
                f"{external_id}|{date_val}|{description}".encode("utf-8")
            ).hexdigest()[:16]

            defaults: dict[str, Any] = {
                "description": description[:500],
                "type": (row.get("type") or "other").strip()[:32],
                "severity": (row.get("severity") or "low").strip()[:16],
                "action_taken": (row.get("action_taken") or "").strip()[:255],
                "date": date_val,
            }
            if "external_ref" in incident_fields:
                defaults["external_ref"] = stable_hash
            defaults = filter_to_model_fields(defaults, Incident)

            if ctx.dry_run:
                result.created += 1
                continue

            lookup: dict[str, Any] = {"student": student, "date": date_val}
            if "external_ref" in incident_fields:
                lookup["external_ref"] = stable_hash
            try:
                obj, created = Incident.objects.update_or_create(**lookup, defaults=defaults)
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"behavior upsert failed for {external_id} @ {date_val}: {type(exc).__name__}: {exc}"
                )
        return result


register("behavior", BehaviorLander())
