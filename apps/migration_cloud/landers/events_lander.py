"""Events lander — persists canonical event rows into ``apps.school_events.SchoolEvent``.

Canonical row shape::

    {
        "title":         "Spring Concert",
        "category":      "concert"|"sports"|"academic"|"social"|"holiday"|"other",
        "starts_at":     "2026-04-10T19:00:00",
        "ends_at":       "2026-04-10T21:30:00",
        "location":      "Main Auditorium",
        "description":   "Annual spring choir + orchestra concert."
    }

Upsert key: (title, starts_at) — historical events are imported as a
read-only timeline; the platform does NOT send notifications or open
registrations for migrated events.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class EventsLander(Lander):
    domain = "events"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.school_events.models import SchoolEvent
        except ImportError as exc:
            raise LanderError(
                f"EventsLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        e_fields = model_field_names(SchoolEvent)

        for row in canonical_rows:
            title = (row.get("title") or "").strip()
            starts = coerce_date(row.get("starts_at") or row.get("start_date") or row.get("date"))
            if not title or starts is None:
                result.quarantined += 1
                result.errors.append(
                    f"events: missing title/starts_at in {row!r}"
                )
                continue
            ends = coerce_date(row.get("ends_at") or row.get("end_date")) or starts
            category = (row.get("category") or "other").strip().lower()
            location = (row.get("location") or "").strip()
            description = (row.get("description") or "").strip()

            defaults: dict[str, Any] = {
                "title": title[:255],
            }
            for src, target in [
                ("description", "description"),
                ("location", "location"),
                ("venue", "venue"),
                ("category", "category"),
                ("event_type", "event_type"),
            ]:
                v = {"description": description, "location": location, "venue": location, "category": category, "event_type": category}[src]
                if target in e_fields and v:
                    defaults[target] = v[:255]
            if "starts_at" in e_fields:
                defaults["starts_at"] = _dt.datetime.combine(starts, _dt.time.min)
            elif "start_date" in e_fields:
                defaults["start_date"] = starts
            if "ends_at" in e_fields:
                defaults["ends_at"] = _dt.datetime.combine(ends, _dt.time(23, 59))
            elif "end_date" in e_fields:
                defaults["end_date"] = ends
            defaults = filter_to_model_fields(defaults, SchoolEvent)

            lookup_kwargs: dict[str, Any] = {"title": title[:255]}
            if "starts_at" in e_fields:
                lookup_kwargs["starts_at"] = defaults.get("starts_at")
            elif "start_date" in e_fields:
                lookup_kwargs["start_date"] = starts

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = SchoolEvent.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = SchoolEvent.objects.update_or_create(
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
                    ctx=ctx, legacy_id=f"{title}:{starts.isoformat()}",
                    canonical_obj=obj, domain="events",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"events upsert failed for {title!r} @ {starts}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("events", EventsLander())
