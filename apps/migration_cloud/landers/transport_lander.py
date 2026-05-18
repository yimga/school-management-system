"""Transport lander — persists canonical transport-route rows into ``apps.schoolops.Route``.

Migration scope: routes (the primary catalog entity). Stops and per-
student bus assignments are written through the catch-all dynamic_field
path until they earn their own first-class landers; this lander only
owns the route catalog itself so re-imports stay clean.

Canonical row shape::

    {
        "route":          "Route 7",            # required — the route name
        "stop":           "Maple & 3rd",        # optional — informational only
        "pickup_time":    "07:15",              # optional
        "dropoff_time":   "15:30",              # optional
        "vehicle":        "Bus 12",             # optional
    }

Upsert key: (school, route name).
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class TransportLander(Lander):
    domain = "transport"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.schoolops.models import Route
        except ImportError as exc:
            raise LanderError(
                f"TransportLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        r_fields = model_field_names(Route)
        seen_routes: set[str] = set()

        for row in canonical_rows:
            route_name = (row.get("route") or row.get("name") or "").strip()
            if not route_name:
                result.quarantined += 1
                result.errors.append(
                    f"transport: missing route name in {row!r}"
                )
                continue
            # Idempotent within the bundle (multiple rows may reference the
            # same route with different stops); only land the route once.
            key = f"{getattr(ctx.school, 'pk', '')}:{route_name.lower()}"
            if key in seen_routes:
                result.skipped += 1
                continue
            seen_routes.add(key)

            defaults: dict[str, Any] = {"name": route_name[:128]}
            if "is_active" in r_fields:
                defaults["is_active"] = True
            if "school" in r_fields and ctx.school is not None:
                defaults["school"] = ctx.school
            defaults = filter_to_model_fields(defaults, Route)

            lookup_kwargs: dict[str, Any] = {"name": route_name[:128]}
            if "school" in r_fields and ctx.school is not None:
                lookup_kwargs["school"] = ctx.school

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = Route.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = Route.objects.update_or_create(
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
                    ctx=ctx, legacy_id=route_name,
                    canonical_obj=obj, domain="transport",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"transport upsert failed for {route_name!r}: {type(exc).__name__}: {exc}"
                )
        return result


register("transport", TransportLander())
