"""Hostel assignment lander — persists per-student room stays.

Promoted v3.29.0: first-class :class:`apps.schoolops.HostelAssignment`
when both the student and the HostelRoom resolve; falls back to
``apps.metadata.DynamicFieldValue`` when the room can't be matched
(out-of-order bundle: hostel/room catalog hasn't landed yet).
Quarantines the row only when the student itself can't be resolved.

Migration scope: the per-student side of the hostel catalog. The sibling
:mod:`hostel_lander` owns the room catalog (``Hostel`` + ``HostelRoom``);
this lander owns the join row that says "student PS-1029 stayed in
Cedar House C-203 from 2025-09-01 to 2026-06-30".

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "hostel":              "Cedar House",
        "room":                "C-203",
        "checkin_date":        "2025-09-01",     # → effective_from
        "checkout_date":       "2026-06-30",     # → effective_to (optional)
        "bed_label":           "Bed 1",          # optional
        "status":              "active",         # one of HostelAssignment choices
        "notes":               "...",            # optional
    }

Upsert keys:
    * First-class path: ``(student, room, effective_from)`` unique-together.
    * DFV fallback path: ``(school, entity_type='student_hostel_assignment',
      entity_id=f"{student.pk}:{room_token}:{checkin_iso}")``.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    resolve_student,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


logger = logging.getLogger(__name__)

_ENTITY_TYPE = "student_hostel_assignment"
_ENTITY_ID_LENGTH_CAP = 96
_PAYLOAD_VALUE_CAP = 128
_FIELD_KEY = "payload"
_PAYLOAD_KEYS = ("hostel", "room", "checkin_date", "checkout_date")
_VALID_STATUSES = ("active", "checked_out", "ended")


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
            from apps.schoolops.models import (
                Hostel,
                HostelAssignment,
                HostelRoom,
            )
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
        hxa_fields = model_field_names(HostelAssignment)
        room_cache: dict[str, Any] = {}

        for row_index, row in enumerate(canonical_rows):
            external_id = (row.get("student_external_id") or "").strip()
            hostel_name = (row.get("hostel") or "").strip()
            room_name = (row.get("room") or "").strip()
            checkin_date = coerce_date(
                row.get("checkin_date") or row.get("effective_from")
            )
            if not external_id or not room_name or checkin_date is None:
                result.quarantined += 1
                result.errors.append(
                    f"hostel_assignments[row={row_index}]: "
                    f"missing student_external_id / room / checkin_date"
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
                    f"hostel_assignments[row={row_index}]: "
                    f"no student with {student_lookup}=<redacted>"
                )
                logger.info(
                    "hostel_assignments quarantine row=%d reason=student_unresolved",
                    row_index,
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

            checkout_date = coerce_date(
                row.get("checkout_date") or row.get("effective_to")
            )
            status_raw = (row.get("status") or "active").strip().lower()
            status = status_raw if status_raw in _VALID_STATUSES else "active"
            bed_label = (row.get("bed_label") or "").strip()[:32]
            notes = (row.get("notes") or "").strip()

            # FIRST-CLASS PATH
            if room is not None:
                defaults: dict[str, Any] = {
                    "effective_to": checkout_date,
                    "status": status,
                    "bed_label": bed_label,
                    "notes": notes,
                }
                defaults = filter_to_model_fields(defaults, HostelAssignment)
                lookup_kwargs: dict[str, Any] = {
                    "student": student,
                    "room": room,
                    "effective_from": checkin_date,
                }
                if "school" in hxa_fields and ctx.school is not None:
                    lookup_kwargs["school"] = ctx.school
                if ctx.dry_run:
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                    exists = HostelAssignment.objects.filter(
                        student=student, room=room, effective_from=checkin_date,
                    ).exists()
                    result.updated += 1 if exists else 0
                    result.created += 0 if exists else 1
                    continue
                try:
                    obj, created = HostelAssignment.objects.update_or_create(
                        defaults=defaults, **lookup_kwargs,
                    )
                except (TypeError, ValueError) as exc:
                    result.quarantined += 1
                    result.errors.append(
                        f"hostel_assignments[row={row_index}]: "
                        f"first-class upsert input error: {type(exc).__name__}"
                    )
                    continue
                except Exception as exc:  # noqa: BLE001
                    logger.info(
                        "hostel_assignments[row=%d]: first-class upsert "
                        "raised %s; falling back to DFV",
                        row_index, type(exc).__name__,
                    )
                else:
                    if created:
                        result.created += 1
                        result.created_ids.append(obj.pk)
                    else:
                        result.updated += 1
                        result.updated_ids_with_old_values.append(
                            {"pk": obj.pk, "old": {k: getattr(obj, k, None)
                                                   for k in defaults}}
                        )
                    record_id_mapping(
                        ctx=ctx,
                        legacy_id=(
                            f"{external_id}:{hostel_name}:{room_name}:"
                            f"{checkin_date.isoformat()}"
                        ),
                        canonical_obj=obj,
                        domain="hostel_assignments",
                    )
                    continue

            # FALLBACK PATH (room unresolved)
            logger.info(
                "hostel_assignments[row=%d]: fallback=DFV reason=room_unresolved",
                row_index,
            )
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
            if checkout_date is not None:
                payload["checkout_date"] = checkout_date.isoformat()
            if bed_label:
                payload["bed_label"] = bed_label
            payload["status"] = status
            if notes:
                payload["notes"] = notes[:_PAYLOAD_VALUE_CAP]
            if room is not None:
                payload["room_pk"] = room.pk

            defaults_dfv: dict[str, Any] = {"value_json": payload}
            defaults_dfv = filter_to_model_fields(defaults_dfv, DynamicFieldValue)

            lookup_kwargs_dfv: dict[str, Any] = {
                "entity_type": _ENTITY_TYPE,
                "entity_id": entity_id,
                "field_key": _FIELD_KEY,
            }
            if "school" in dfv_fields and ctx.school is not None:
                lookup_kwargs_dfv["school"] = ctx.school

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = DynamicFieldValue.objects.filter(**lookup_kwargs_dfv).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = DynamicFieldValue.objects.update_or_create(
                    defaults=defaults_dfv, **lookup_kwargs_dfv,
                )
            except (TypeError, ValueError) as exc:
                result.quarantined += 1
                result.errors.append(
                    f"hostel_assignments[row={row_index}]: "
                    f"DFV upsert input error: {type(exc).__name__}"
                )
                continue
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"hostel_assignments[row={row_index}] DFV upsert failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            if created:
                result.created += 1
                result.created_ids.append(obj.pk)
            else:
                result.updated += 1
                result.updated_ids_with_old_values.append(
                    {"pk": obj.pk, "old": {k: getattr(obj, k, None)
                                           for k in defaults_dfv}}
                )
            record_id_mapping(
                ctx=ctx,
                legacy_id=f"{external_id}:{hostel_name}:{room_name}:{checkin_iso}",
                canonical_obj=obj, domain="hostel_assignments",
            )
        return result


register("hostel_assignments", HostelAssignmentLander())

__all__ = ["HostelAssignmentLander"]
