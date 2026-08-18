"""Transport assignment lander — persists per-student route/stop assignments.

Promoted v3.29.0: first-class :class:`apps.schoolops.TransportAssignment`
when both the student and route resolve; falls back to
``apps.metadata.DynamicFieldValue`` when the route can't be matched
(out-of-order bundle: route catalog hasn't landed yet). Quarantines the
row only when the student itself can't be resolved.

Graceful degradation:
    The "Companion app + canonical template" pipeline can deliver
    bundles in any order — assignment rows can arrive before the route
    catalog. To never drop data, this lander preserves the v3.28 DFV
    payload as a fallback path. A later re-run of the assignment bundle
    after the catalog lands will resolve to the first-class model
    (idempotent via the unique ``(student, route, effective_from)``
    constraint).

Migration scope: the per-student side of the transport catalog. The
sibling :mod:`transport_lander` owns the route catalog itself; this
lander owns the join row that says "student PS-1029 rides Route 7 from
Maple & 3rd, picked up at 07:15".

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "route":               "Route 7",
        "stop":                "Maple & 3rd",        # optional → pickup_stop
        "dropoff_stop":        "Elm & 5th",          # optional
        "pickup_time":         "07:15",              # informational only
        "dropoff_time":        "15:30",              # informational only
        "vehicle":             "Bus 12",             # informational only
        "effective_from":      "2025-09-01",         # ISO date — required for first-class
        "effective_to":        "2026-06-30",         # optional
        "status":              "active",             # one of TransportAssignment choices
        "notes":               "AM only",            # optional
    }

Upsert keys:
    * First-class path: ``(student, route, effective_from)`` unique-together.
    * DFV fallback path: ``(school, entity_type='student_transport_assignment',
      entity_id=f"{student.pk}:{route_name}")`` — preserved from v3.28 so
      a re-import after the catalog lands deterministically updates the
      same DFV row before the codebase upgrades it via
      ``promote_dyna_assignments`` mgmt command.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Iterator

from ._helpers import (
    unresolved_student_reason,
    student_name_from_row,
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    resolve_student,
    row_savepoint,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


logger = logging.getLogger(__name__)

_ENTITY_TYPE = "student_transport_assignment"
_LEGACY_ID_LENGTH_CAP = 128
_ENTITY_ID_LENGTH_CAP = 64
_FIELD_KEY = "payload"
_PAYLOAD_KEYS = ("route", "stop", "pickup_time", "dropoff_time", "vehicle")
_VALID_STATUSES = ("active", "paused", "ended")


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
            from apps.schoolops.models import Route, TransportAssignment
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

        for row_index, row in enumerate(canonical_rows):
            external_id = (row.get("student_external_id") or "").strip()
            route_name = (row.get("route") or "").strip()
            if not (external_id or student_name_from_row(row)) or not route_name:
                result.quarantined += 1
                result.errors.append(
                    f"transport_assignments[row={row_index}]: "
                    f"missing student_external_id or route"
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
                    f"[row={row_index}] "
                    + unresolved_student_reason(
                        domain="transport_assignments",
                        ctx=ctx,
                        student_model=StudentProfile,
                        row=row,
                        external_id=external_id,
                        lookup_field=student_lookup,
                    )
                )
                logger.info(
                    "transport_assignments quarantine row=%d reason=student_unresolved",
                    row_index,
                )
                continue

            # Best-effort link to a previously-landed Route. If the route catalog
            # row hasn't shipped yet (out-of-order bundle), the assignment falls
            # back to DynamicFieldValue with the route name on the payload.
            route_key = f"{getattr(ctx.school, 'pk', '')}:{route_name.lower()}"
            route = route_cache.get(route_key)
            if route is None and route_key not in route_cache:
                route_filter: dict[str, Any] = {"name": route_name[:128]}
                if "school" in route_fields and ctx.school is not None:
                    route_filter["school"] = ctx.school
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                route = Route.objects.filter(**route_filter).first()
                route_cache[route_key] = route

            effective_from = coerce_date(row.get("effective_from"))
            effective_to = coerce_date(row.get("effective_to"))
            status_raw = (row.get("status") or "active").strip().lower()
            status = status_raw if status_raw in _VALID_STATUSES else "active"
            pickup_stop = (
                row.get("pickup_stop") or row.get("stop") or ""
            ).strip()[:128]
            dropoff_stop = (row.get("dropoff_stop") or "").strip()[:128]
            notes = (row.get("notes") or "").strip()

            # FIRST-CLASS PATH: both ends of the join resolved + we have an
            # effective_from to anchor the unique constraint.
            if route is not None and effective_from is not None:
                defaults: dict[str, Any] = {
                    "effective_to": effective_to,
                    "status": status,
                    "pickup_stop": pickup_stop,
                    "dropoff_stop": dropoff_stop,
                    "notes": notes,
                }
                defaults = filter_to_model_fields(defaults, TransportAssignment)
                lookup_kwargs: dict[str, Any] = {
                    "student": student,
                    "route": route,
                    "effective_from": effective_from,
                }
                if (
                    "school" in model_field_names(TransportAssignment)
                    and ctx.school is not None
                ):
                    lookup_kwargs["school"] = ctx.school
                if ctx.dry_run:
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                    exists = TransportAssignment.objects.filter(
                        student=student,
                        route=route,
                        effective_from=effective_from,
                    ).exists()
                    result.updated += 1 if exists else 0
                    result.created += 0 if exists else 1
                    continue
                try:
                    with row_savepoint():  # atomic-apply isolation
                        obj, created = TransportAssignment.objects.update_or_create(
                            defaults=defaults, **lookup_kwargs,
                        )
                except (TypeError, ValueError) as exc:
                    result.quarantined += 1
                    result.errors.append(
                        f"transport_assignments[row={row_index}]: "
                        f"first-class upsert input error: {type(exc).__name__}"
                    )
                    continue
                except Exception as exc:  # noqa: BLE001
                    # IntegrityError / FieldError / DatabaseError — fall through
                    # to DFV so the row is captured for later promotion.
                    logger.info(
                        "transport_assignments[row=%d]: first-class upsert "
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
                        legacy_id=f"{external_id}:{route_name}",
                        canonical_obj=obj,
                        domain="transport_assignments",
                    )
                    continue

            # FALLBACK PATH (route unresolved OR no effective_from): keep the
            # data in DynamicFieldValue so a later promotion run can recover
            # it once the catalog row lands.
            logger.info(
                "transport_assignments[row=%d]: fallback=DFV reason=%s",
                row_index,
                "route_unresolved" if route is None else "missing_effective_from",
            )
            route_token = str(getattr(route, "pk", "") or route_name)[:32]
            entity_id = f"{student.pk}:{route_token}"[:_ENTITY_ID_LENGTH_CAP]

            payload: dict[str, Any] = {
                k: str(row[k])[:_LEGACY_ID_LENGTH_CAP]
                for k in _PAYLOAD_KEYS
                if row.get(k) not in (None, "")
            }
            payload["student_external_id"] = external_id[:_LEGACY_ID_LENGTH_CAP]
            if effective_from is not None:
                payload["effective_from"] = effective_from.isoformat()
            if effective_to is not None:
                payload["effective_to"] = effective_to.isoformat()
            if pickup_stop:
                payload["pickup_stop"] = pickup_stop
            if dropoff_stop:
                payload["dropoff_stop"] = dropoff_stop
            payload["status"] = status
            if notes:
                payload["notes"] = notes[:_LEGACY_ID_LENGTH_CAP]
            if route is not None:
                payload["route_pk"] = route.pk

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
                with row_savepoint():  # atomic-apply isolation
                    obj, created = DynamicFieldValue.objects.update_or_create(
                        defaults=defaults_dfv, **lookup_kwargs_dfv,
                    )
            except (TypeError, ValueError) as exc:
                result.quarantined += 1
                result.errors.append(
                    f"transport_assignments[row={row_index}]: "
                    f"DFV upsert input error: {type(exc).__name__}"
                )
                continue
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"transport_assignments[row={row_index}] DFV upsert failed: "
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
                ctx=ctx, legacy_id=f"{external_id}:{route_name}",
                canonical_obj=obj, domain="transport_assignments",
            )
        return result


register("transport_assignments", TransportAssignmentLander())


# Re-export for type-checking + so external promotion script doesn't have to
# import private symbols.
__all__ = ["TransportAssignmentLander"]


def _today() -> _dt.date:  # pragma: no cover — convenience for tests
    return _dt.date.today()
