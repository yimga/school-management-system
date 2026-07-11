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
    resolve_student,
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
            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
            )
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"health: no student with {student_lookup}={external_id!r}"
                )
                continue

            # HealthRecord.record_type is max_length=32. The source event date +
            # provider + follow-up have no dedicated columns (recorded_at is
            # auto_now_add = server insert time), so fold them into notes — that
            # keeps the date visible AND lets (school, student, record_type, notes)
            # key an idempotent upsert that preserves DISTINCT events instead of
            # collapsing every same-type record into one row.
            record_type = category[:32]
            note_body = (row.get("description") or row.get("notes") or "").strip()
            if date_val:
                note_body = f"[{date_val.isoformat()}] {note_body}".strip()
            provider = (row.get("provider") or "").strip()
            if provider:
                note_body = f"{note_body} (provider: {provider})".strip()
            follow_up = (row.get("follow_up") or "").strip()
            if follow_up:
                note_body = f"{note_body} [follow-up: {follow_up}]".strip()
            note_body = note_body[:2000]

            defaults: dict[str, Any] = {"confidential": truthy(row.get("confidential"))}
            defaults = filter_to_model_fields(defaults, HealthRecord)

            # school is a required NOT NULL FK; canonical health rows carry none,
            # so bind the bundle's school or every insert IntegrityErrors.
            lookup_kwargs: dict[str, Any] = {"student": student}
            if "school" in h_fields and ctx.school is not None:
                lookup_kwargs["school"] = ctx.school
            if "record_type" in h_fields:
                lookup_kwargs["record_type"] = record_type
            if "notes" in h_fields:
                lookup_kwargs["notes"] = note_body

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = HealthRecord.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import upsert_with_conflict_detection
                _hl_legacy = f"{external_id}:{date_val.isoformat() if date_val else ''}:{category}"
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="health", model=HealthRecord,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=_hl_legacy,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=_hl_legacy, canonical_obj=obj, domain="health")
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
                    ctx=ctx,
                    legacy_id=_hl_legacy,
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
