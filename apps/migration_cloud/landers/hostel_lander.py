"""Hostel lander — persists canonical hostel-room rows into ``apps.schoolops.HostelRoom``.

Migration scope: room catalog. Per-student room assignments are handled by the
sibling ``hostel_assignments`` lander; this lander owns the room catalog so
re-imports stay clean.

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

from django.core.exceptions import FieldDoesNotExist

from ._helpers import (
    coerce_int,
    filter_to_model_fields,
    model_field_names,
    normalize_canonical_row,
    record_id_mapping,
    record_row_error,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


def _max_length(model, field: str) -> int | None:
    """The column's OWN declared ``max_length`` — the only honest clip width.

    This lander used to restate the widths as literals and they had drifted:
    ``HostelRoom.name`` was clipped to 64 against a ``max_length=60`` column
    and ``Hostel.name`` to 128 against 120. SQLite does not enforce
    ``max_length``, so a name landing in the 61-64 (or 121-128) band stored
    fine in dev and PostgreSQL refused it in production with ``value too long
    for type character varying(60)`` — the row quarantined only on the engine
    nobody tests against. Reading the width off ``_meta`` means the next
    ``max_length`` change cannot reintroduce the drift. ``None`` (no declared
    width, or the field is absent on this deploy) slices to the whole string.
    """
    try:
        return model._meta.get_field(field).max_length
    except FieldDoesNotExist:
        return None


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
        # Clip widths come from the columns themselves, once per bundle.
        h_name_cap = _max_length(Hostel, "name")
        r_name_cap = _max_length(HostelRoom, "name")
        hostel_cache: dict[str, Any] = {}

        for row in canonical_rows:
            row = normalize_canonical_row("hostel", row, ctx)
            hostel_name = (row.get("hostel") or row.get("hostel_name") or "Main Hostel").strip()
            room_name = (row.get("room") or row.get("room_name") or row.get("name") or "").strip()
            if not room_name:
                record_row_error(
                    result,
                    row,
                    f"hostel: missing room name in {row!r}",
                    reason_code=MISSING_REQUIRED, field="name",
                )
                continue

            cache_key = f"{getattr(ctx.school, 'pk', '')}:{hostel_name.lower()}"
            hostel = hostel_cache.get(cache_key)
            if hostel is None:
                hostel_defaults: dict[str, Any] = {"name": hostel_name[:h_name_cap]}
                if "school" in h_fields and ctx.school is not None:
                    hostel_defaults["school"] = ctx.school
                hostel_defaults = filter_to_model_fields(hostel_defaults, Hostel)
                hostel_lookup: dict[str, Any] = {"name": hostel_name[:h_name_cap]}
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
                        record_row_error(
                            result,
                            row,
                            f"hostel parent upsert failed for {hostel_name!r}: "
                            f"{type(exc).__name__}: {exc}",
                            reason_code=LANDER_ERROR,
                        )
                        continue
                hostel_cache[cache_key] = hostel

            # NOT ``or 1``: that folds an explicit 0 (and a blank, and an
            # unparseable value) into 1, inventing a bed the source never
            # declared. ``None`` is dropped by ``filter_to_model_fields``
            # below, so a missing capacity takes the column default (1) on
            # create and is left untouched on update; a real 0 survives.
            capacity = coerce_int(row.get("capacity"))
            defaults: dict[str, Any] = {
                "name": room_name[:r_name_cap],
                "capacity": capacity,
            }
            if "hostel" in r_fields and hostel is not None:
                defaults["hostel"] = hostel
            defaults = filter_to_model_fields(defaults, HostelRoom)

            lookup_kwargs: dict[str, Any] = {"name": room_name[:r_name_cap]}
            if "hostel" in r_fields and hostel is not None:
                lookup_kwargs["hostel"] = hostel

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = HostelRoom.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import upsert_with_conflict_detection
                _ho_legacy = f"{hostel_name}:{room_name}"
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="hostel", model=HostelRoom,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=_ho_legacy,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=_ho_legacy, canonical_obj=obj, domain="hostel")
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
                    ctx=ctx, legacy_id=_ho_legacy,
                    canonical_obj=obj, domain="hostel",
                )
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"hostel upsert failed for {hostel_name}/{room_name!r}: "
                    f"{type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


register("hostel", HostelLander())
