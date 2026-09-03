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
    normalize_canonical_row,
    record_id_mapping,
    record_row_error,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


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
            row = normalize_canonical_row("events", row, ctx)
            title = (row.get("title") or "").strip()
            starts = coerce_date(row.get("starts_at") or row.get("start_date") or row.get("date"))
            if not title or starts is None:
                record_row_error(
                    result,
                    row,
                    f"events: missing title/starts_at in {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue
            ends = coerce_date(row.get("ends_at") or row.get("end_date")) or starts
            category = (row.get("category") or "other").strip().lower()
            location = (row.get("location") or "").strip()
            description = (row.get("description") or "").strip()

            defaults: dict[str, Any] = {"title": title[:255]}
            if "description" in e_fields and description:
                defaults["description"] = description
            # SchoolEvent's real datetime columns are start_at/end_at (start_at is
            # required) — NOT starts_at/start_date. venue is an FK to EventVenue;
            # assigning the location STRING to it raised ValueError, so location +
            # category go into the metadata JSON instead of a phantom/FK column.
            if "start_at" in e_fields:
                defaults["start_at"] = _dt.datetime.combine(starts, _dt.time.min)
            elif "starts_at" in e_fields:
                defaults["starts_at"] = _dt.datetime.combine(starts, _dt.time.min)
            elif "start_date" in e_fields:
                defaults["start_date"] = starts
            if "end_at" in e_fields:
                defaults["end_at"] = _dt.datetime.combine(ends, _dt.time(23, 59))
            elif "ends_at" in e_fields:
                defaults["ends_at"] = _dt.datetime.combine(ends, _dt.time(23, 59))
            elif "end_date" in e_fields:
                defaults["end_date"] = ends
            if "metadata" in e_fields:
                meta: dict[str, Any] = {"source": "migration_cloud"}
                if location:
                    meta["location"] = location[:255]
                if category:
                    meta["category"] = category[:64]
                defaults["metadata"] = meta
            # school is a required NOT NULL FK; canonical event rows carry none.
            if "school" in e_fields and ctx.school is not None:
                defaults["school"] = ctx.school
            defaults = filter_to_model_fields(defaults, SchoolEvent)

            # slug is unique per (school, slug); derive it from title+date so
            # recurring same-titled events don't collide and re-runs are idempotent.
            slug = ""
            if "slug" in e_fields:
                from django.utils.text import slugify
                slug = (slugify(f"{title}-{starts.isoformat()}") or "event")[:100]

            lookup_kwargs: dict[str, Any] = {}
            if "school" in e_fields and ctx.school is not None:
                lookup_kwargs["school"] = ctx.school
            if slug:
                lookup_kwargs["slug"] = slug
            else:
                lookup_kwargs["title"] = title[:255]

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = SchoolEvent.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import upsert_with_conflict_detection
                _ev_legacy = f"{title}:{starts.isoformat()}"
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="events", model=SchoolEvent,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=_ev_legacy,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=_ev_legacy, canonical_obj=obj, domain="events")
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
                    ctx=ctx, legacy_id=_ev_legacy,
                    canonical_obj=obj, domain="events",
                )
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"events upsert failed for {title!r} @ {starts}: "
                    f"{type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


register("events", EventsLander())
