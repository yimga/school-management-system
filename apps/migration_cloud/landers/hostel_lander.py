"""Hostel lander — persists canonical hostel-room rows into ``apps.schoolops.HostelRoom``.

Migration scope: room catalog. Per-student room assignments are
deferred to the dynamic_field path until a `HostelAssignment` lander
ships; this lander owns the room catalog so re-imports stay clean.

Canonical row shape::

    {
        "hostel":   "Cedar House",          # required — parent hostel
        "room":     "C-203",                # required — room name/number
        "capacity": 4,                       # optional, defaults to 1
    }

Upsert key: (hostel, room name).
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_int,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class HostelLander(Lander):
    domain = "hostel"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.schoolops.models import Hostel, HostelRoom
        except ImportError as exc:
            raise LanderError(
                f"HostelLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        h_fields = model_field_names(Hostel)
        r_fields = model_field_names(HostelRoom)
        hostel_cache: dict[str, Any] = {}

        for row in canonical_rows:
            hostel_name = (row.get("hostel") or row.get("hostel_name") or "Main Hostel").strip()
            room_name = (row.get("room") or row.get("room_name") or row.get("name") or "").strip()
            if not room_name:
                result.quarantined += 1
                result.errors.append(
                    f"hostel: missing room name in {row!r}"
                )
                continue

            cache_key = f"{getattr(ctx.school, 'pk', '')}:{hostel_name.lower()}"
            hostel = hostel_cache.get(cache_key)
            if hostel is None:
                hostel_defaults: dict[str, Any] = {"name": hostel_name[:128]}
                if "school" in h_fields and ctx.school is not None:
                    hostel_defaults["school"] = ctx.school
                hostel_defaults = filter_to_model_fields(hostel_defaults, Hostel)
                hostel_lookup: dict[str, Any] = {"name": hostel_name[:128]}
                if "school" in h_fields and ctx.school is not None:
                    hostel_lookup["school"] = ctx.school
                if ctx.dry_run:
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                    hostel = Hostel.objects.filter(**hostel_lookup).first()
                else:
                    try:
                        hostel, _ = Hostel.objects.update_or_create(
                            defaults=hostel_defaults, **hostel_lookup,
                        )
                    except Exception as exc:  # noqa: BLE001
                        result.quarantined += 1
                        result.errors.append(
                            f"hostel parent upsert failed for {hostel_name!r}: "
                            f"{type(exc).__name__}: {exc}"
                        )
                        continue
                hostel_cache[cache_key] = hostel

            capacity = coerce_int(row.get("capacity")) or 1
            defaults: dict[str, Any] = {
                "name": room_name[:64],
                "capacity": capacity,
            }
            if "hostel" in r_fields and hostel is not None:
                defaults["hostel"] = hostel
            defaults = filter_to_model_fields(defaults, HostelRoom)

            lookup_kwargs: dict[str, Any] = {"name": room_name[:64]}
            if "hostel" in r_fields and hostel is not None:
                lookup_kwargs["hostel"] = hostel

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = HostelRoom.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = HostelRoom.objects.update_or_create(
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
                    ctx=ctx, legacy_id=f"{hostel_name}:{room_name}",
                    canonical_obj=obj, domain="hostel",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"hostel upsert failed for {hostel_name}/{room_name!r}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("hostel", HostelLander())
