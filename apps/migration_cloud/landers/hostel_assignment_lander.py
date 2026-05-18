"""Hostel assignment lander — persists per-student room stays.

Migration scope: the per-student side of the hostel catalog. The sibling
:mod:`hostel_lander` owns the room catalog (``Hostel`` + ``HostelRoom``);
this lander owns the join row that says "student PS-1029 stayed in
Cedar House C-203 from 2025-09-01 to 2026-06-30".

Target model — fallback rationale:
    The tenant ``apps.schoolops`` package does not currently ship a
    first-class ``HostelAssignment`` / ``StudentHostel`` model. Until
    one lands, this lander persists each row into
    ``apps.metadata.DynamicFieldValue`` keyed by
    ``entity_type='student_hostel_assignment'`` and
    ``entity_id=<student.pk>:<room.pk-or-name>:<checkin_iso>``. A
    student can have multiple stays across years, so the check-in date
    is part of the key (matches the spec's upsert key (student, room,
    checkin_date)). The full canonical payload is stored on
    ``value_json`` for a future first-class promotion.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "hostel":              "Cedar House",
        "room":                "C-203",
        "checkin_date":        "2025-09-01",        # ISO date
        "checkout_date":       "2026-06-30",        # optional
    }

Upsert key: ``(school, entity_type='student_hostel_assignment',
entity_id=f"{student.pk}:{room_token}:{checkin_iso}")``.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


_ENTITY_TYPE = "student_hostel_assignment"
_ENTITY_ID_LENGTH_CAP = 96
_PAYLOAD_VALUE_CAP = 128
_FIELD_KEY = "payload"
_PAYLOAD_KEYS = ("hostel", "room", "checkin_date", "checkout_date")


class HostelAssignmentLander(Lander):
    domain = "hostel_assignments"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.metadata.models import DynamicFieldValue
            from apps.people.models import StudentProfile
            from apps.schoolops.models import Hostel, HostelRoom
        except ImportError as exc:
            raise LanderError(
                f"HostelAssignmentLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        hostel_fields = model_field_names(Hostel)
        room_fields = model_field_names(HostelRoom)
        dfv_fields = model_field_names(DynamicFieldValue)
        room_cache: dict[str, Any] = {}

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            hostel_name = (row.get("hostel") or "").strip()
            room_name = (row.get("room") or "").strip()
            checkin_date = coerce_date(row.get("checkin_date"))
            if not external_id or not room_name or checkin_date is None:
                result.quarantined += 1
                result.errors.append(
                    f"hostel_assignments: missing student/room/checkin_date in {row!r}"
                )
                continue

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"hostel_assignments: no student with "
                    f"{student_lookup}={external_id!r}"
                )
                continue

            cache_key = (
                f"{getattr(ctx.school, 'pk', '')}:"
                f"{hostel_name.lower()}:{room_name.lower()}"
            )
            room = room_cache.get(cache_key)
            if room is None and cache_key not in room_cache:
                hostel_filter: dict[str, Any] = {"name": hostel_name[:128]}
                if "school" in hostel_fields and ctx.school is not None:
                    hostel_filter["school"] = ctx.school
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                hostel = (
                    Hostel.objects.filter(**hostel_filter).first()
                    if hostel_name else None
                )
                room_filter: dict[str, Any] = {"name": room_name[:64]}
                if "hostel" in room_fields and hostel is not None:
                    room_filter["hostel"] = hostel
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                room = HostelRoom.objects.filter(**room_filter).first()
                room_cache[cache_key] = room

            room_token = str(getattr(room, "pk", "") or room_name)[:32]
            checkin_iso = checkin_date.isoformat()
            entity_id = f"{student.pk}:{room_token}:{checkin_iso}"[:_ENTITY_ID_LENGTH_CAP]

            payload: dict[str, Any] = {
                k: str(row[k])[:_PAYLOAD_VALUE_CAP]
                for k in _PAYLOAD_KEYS
                if row.get(k) not in (None, "")
            }
            payload["student_external_id"] = external_id[:_PAYLOAD_VALUE_CAP]
            payload["checkin_date"] = checkin_iso
            checkout_date = coerce_date(row.get("checkout_date"))
            if checkout_date is not None:
                payload["checkout_date"] = checkout_date.isoformat()
            if room is not None:
                payload["room_pk"] = room.pk

            defaults: dict[str, Any] = {"value_json": payload}
            defaults = filter_to_model_fields(defaults, DynamicFieldValue)

            lookup_kwargs: dict[str, Any] = {
                "entity_type": _ENTITY_TYPE,
                "entity_id": entity_id,
                "field_key": _FIELD_KEY,
            }
            if "school" in dfv_fields and ctx.school is not None:
                lookup_kwargs["school"] = ctx.school

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = DynamicFieldValue.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = DynamicFieldValue.objects.update_or_create(
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
                    legacy_id=f"{external_id}:{hostel_name}:{room_name}:{checkin_iso}",
                    canonical_obj=obj, domain="hostel_assignments",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"hostel_assignments upsert failed for "
                    f"{external_id}/{room_name!r}@{checkin_iso}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("hostel_assignments", HostelAssignmentLander())
