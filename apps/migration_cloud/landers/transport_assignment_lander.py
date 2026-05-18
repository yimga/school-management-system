"""Transport assignment lander — persists per-student route/stop assignments.

Migration scope: the per-student side of the transport catalog. The
sibling :mod:`transport_lander` owns the route catalog itself; this
lander owns the join row that says "student PS-1029 rides Route 7 from
Maple & 3rd, picked up at 07:15".

Target model — fallback rationale:
    The tenant ``apps.schoolops`` package does not currently ship a
    first-class ``TransportAssignment`` / ``StudentTransport`` model. The
    closest catalog entities are ``Route``, ``Stop``, and ``Bus`` (all
    school-scoped, none with a student FK). Until a first-class
    assignment model lands, this lander persists each row into
    ``apps.metadata.DynamicFieldValue`` keyed by
    ``entity_type='student_transport_assignment'`` and
    ``entity_id=<student.pk>:<route_name>``. The full canonical payload
    (route / stop / pickup_time / dropoff_time / vehicle) is stored on
    ``value_json`` so a future first-class lander can read these rows
    and promote them without a re-import.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "route":               "Route 7",
        "stop":                "Maple & 3rd",        # optional
        "pickup_time":         "07:15",              # optional
        "dropoff_time":        "15:30",              # optional
        "vehicle":             "Bus 12",             # optional
    }

Upsert key: ``(school, entity_type='student_transport_assignment', entity_id=f"{student.pk}:{route.pk or route_name}")``
— a student can be on multiple routes (split AM/PM), so the route is part
of the key. Re-running the same bundle never duplicates the row.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


_ENTITY_TYPE = "student_transport_assignment"
_LEGACY_ID_LENGTH_CAP = 128
_ENTITY_ID_LENGTH_CAP = 64
_FIELD_KEY = "payload"
_PAYLOAD_KEYS = ("route", "stop", "pickup_time", "dropoff_time", "vehicle")


class TransportAssignmentLander(Lander):
    domain = "transport_assignments"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.metadata.models import DynamicFieldValue
            from apps.people.models import StudentProfile
            from apps.schoolops.models import Route
        except ImportError as exc:
            raise LanderError(
                f"TransportAssignmentLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        route_fields = model_field_names(Route)
        dfv_fields = model_field_names(DynamicFieldValue)
        route_cache: dict[str, Any] = {}

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            route_name = (row.get("route") or "").strip()
            if not external_id or not route_name:
                result.quarantined += 1
                result.errors.append(
                    f"transport_assignments: missing student/route in {row!r}"
                )
                continue

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"transport_assignments: no student with "
                    f"{student_lookup}={external_id!r}"
                )
                continue

            # Best-effort link to a previously-landed Route. If the route catalog
            # row hasn't shipped yet (out-of-order bundle), the assignment still
            # lands with the route name on the payload.
            route_key = f"{getattr(ctx.school, 'pk', '')}:{route_name.lower()}"
            route = route_cache.get(route_key)
            if route is None and route_key not in route_cache:
                route_filter: dict[str, Any] = {"name": route_name[:128]}
                if "school" in route_fields and ctx.school is not None:
                    route_filter["school"] = ctx.school
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                route = Route.objects.filter(**route_filter).first()
                route_cache[route_key] = route

            route_token = str(getattr(route, "pk", "") or route_name)[:32]
            entity_id = f"{student.pk}:{route_token}"[:_ENTITY_ID_LENGTH_CAP]

            payload: dict[str, Any] = {
                k: str(row[k])[:_LEGACY_ID_LENGTH_CAP]
                for k in _PAYLOAD_KEYS
                if row.get(k) not in (None, "")
            }
            payload["student_external_id"] = external_id[:_LEGACY_ID_LENGTH_CAP]
            if route is not None:
                payload["route_pk"] = route.pk

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
                    ctx=ctx, legacy_id=f"{external_id}:{route_name}",
                    canonical_obj=obj, domain="transport_assignments",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"transport_assignments upsert failed for "
                    f"{external_id}/{route_name!r}: {type(exc).__name__}: {exc}"
                )
        return result


register("transport_assignments", TransportAssignmentLander())
