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

Upsert key: (student, date, incident_type, description). ``external_ref`` is
NOT a model field, so the DB lookup uses real columns to keep distinct
same-day incidents distinct. Defensive: never aborts the bundle on one bad row.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    record_row_error,
    resolve_student,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


# Canonical behavior tokens -> real Incident choice VALUES. Verified against
# apps.academics.Incident: Type = TARDINESS / BEHAVIOR / ABSENCE / OTHER;
# Severity = LOW / MEDIUM / HIGH. The old catch-all wrote the raw token into a
# phantom ``type`` kwarg (the field is ``incident_type``) + a free-text
# ``severity``, so filter_to_model_fields dropped ``type`` entirely and every
# incident landed as the model default (OTHER / MEDIUM) with the distinction
# lost. Unmapped tokens fall back to the model defaults.
_INCIDENT_TYPE_MAP = {
    "tardy": "TARDINESS",
    "tardiness": "TARDINESS",
    "late": "TARDINESS",
    "fight": "BEHAVIOR",
    "behavior": "BEHAVIOR",
    "behaviour": "BEHAVIOR",
    "misconduct": "BEHAVIOR",
    "disruption": "BEHAVIOR",
    "absence": "ABSENCE",
    "absent": "ABSENCE",
    "unexcused": "ABSENCE",
    "truancy": "ABSENCE",
}
_INCIDENT_TYPE_DEFAULT = "OTHER"
_SEVERITY_MAP = {
    "low": "LOW",
    "med": "MEDIUM",
    "medium": "MEDIUM",
    "high": "HIGH",
}
_SEVERITY_DEFAULT = "MEDIUM"


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
                record_row_error(
                    result, row, "behavior: missing student/date/description"
                )
                continue
            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
            )
            if student is None:
                record_row_error(
                    result, row, f"behavior: no student with {student_lookup}={external_id!r}"
                )
                continue

            incident_type = _INCIDENT_TYPE_MAP.get(
                (row.get("type") or "").strip().lower(), _INCIDENT_TYPE_DEFAULT
            )
            severity = _SEVERITY_MAP.get(
                (row.get("severity") or "").strip().lower(), _SEVERITY_DEFAULT
            )
            # Discriminator for the id-mapping legacy key only. The model has no
            # external_ref column, so it can't disambiguate in the DB lookup;
            # incident_type + description do that below.
            disc = hashlib.sha256(
                f"{external_id}|{date_val}|{incident_type}|{description}".encode("utf-8"),
                usedforsecurity=False,
            ).hexdigest()[:16]

            defaults: dict[str, Any] = {
                "description": description[:500],
                "incident_type": incident_type,
                "severity": severity,
                "date": date_val,
            }
            defaults = filter_to_model_fields(defaults, Incident)

            if ctx.dry_run:
                result.created += 1
                continue

            # Same-day collision fix: the old lookup degraded to (student, date)
            # because external_ref isn't a field, so a morning tardy and an
            # afternoon fight collapsed into ONE Incident. Enrich the key with
            # incident_type + the (truncated) description so genuinely distinct
            # same-day incidents stay distinct; two identical rows still dedup.
            lookup: dict[str, Any] = {
                "student": student,
                "date": date_val,
                "incident_type": incident_type,
                "description": description[:500],
            }
            if "school" in incident_fields and ctx.school is not None:
                lookup["school"] = ctx.school
            try:
                from ._helpers import record_id_mapping, upsert_with_conflict_detection
                _bh_legacy = f"{external_id}:{date_val}:{incident_type}:{disc}"[:128]
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="behavior", model=Incident,
                    lookup=lookup, defaults=defaults, legacy_id=_bh_legacy,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=_bh_legacy, canonical_obj=obj, domain="behavior")
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                record_id_mapping(
                    ctx=ctx, legacy_id=_bh_legacy,
                    canonical_obj=obj, domain="behavior",
                )
                # ``action_taken`` has no Incident column. Preserve it (when
                # present) on the metadata DynamicFieldValue engine in the
                # correct shape rather than passing a phantom kwarg that gets
                # silently dropped.
                _persist_behavior_extras(
                    ctx=ctx, incident_pk=obj.pk, row=row, result=result,
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"behavior upsert failed for {external_id} @ {date_val}: {type(exc).__name__}: {exc}"
                )
        return result


def _persist_behavior_extras(
    *, ctx: LanderContext, incident_pk: int, row: dict[str, Any], result: LanderResult,
) -> None:
    """Write behavior-only fields not present on Incident to DynamicFieldValue.

    Currently just ``action_taken``. Best-effort — a failure is recorded on the
    result (visible), never silently swallowed, and never blocks the incident.
    """
    action_taken = (row.get("action_taken") or "").strip()
    if not action_taken:
        return
    try:
        from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
    except Exception as exc:  # noqa: BLE001
        result.errors.append(
            f"behavior extras: metadata models unavailable: {type(exc).__name__}"
        )
        return
    try:
        DynamicFieldDefinition.objects.get_or_create(
            entity_type="incident",
            field_key="action_taken",
            school=ctx.school,
            defaults={"label": "Action taken", "data_type": "json"},
        )
        DynamicFieldValue.objects.update_or_create(
            entity_type="incident",
            entity_id=str(incident_pk)[:64],
            field_key="action_taken",
            defaults=filter_to_model_fields(
                {"value_json": {"v": action_taken[:1024]}, "school": ctx.school},  # magic-number-allow: defensive DFV value cap
                DynamicFieldValue,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — extras are best-effort, recorded
        result.errors.append(
            f"behavior extras write failed: {type(exc).__name__}: {exc}"
        )


register("behavior", BehaviorLander())
