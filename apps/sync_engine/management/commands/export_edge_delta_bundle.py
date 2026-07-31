"""Package a tenant's recently-changed records into a signed delta bundle for
edge -> operator sync (Tier 3 Slice 2, the offline-capture half).

A sovereign edge box runs this to collect UPDATES to records that already exist
upstream on the operator -- identity guaranteed by Slice 0's pk-preserving clone,
so a row edited on the box carries the same pk on the operator -- since a cursor,
and writes a signed delta bundle. The bundle is exactly what the operator's
``/api/v1/sync/bundle/upload/`` receiver (Slice 1) consumes; the authenticated
upload over the network is Slice 3 (it needs the per-box machine credential).

Scope / semantics (honest limits):
  * UPDATE-only. The operator applies via ``apply_changes``, which does
    ``model.objects.get(pk=...)`` -- it updates existing rows, it does not INSERT.
    Brand-new edge rows (e.g. a new enrollment created offline) are NOT synced by
    this command; new-row upsert + reconciliation is Slice 4.
  * Last-writer-wins per record. Each row carries the whole allowed-field snapshot
    + the record's ``updated_at``; the receiver applies only when the bundle's
    ``updated_at`` is newer than the operator's copy, else it records a
    ``SyncConflict`` (no silent overwrite).
  * Entity set + field allowlist come from ``apps.api.sync_services`` (the SAME SOT
    the receiver validates against), so producer and applier never drift.

    python manage.py export_edge_delta_bundle --slug gilead-tech \
        --since 2026-07-01T00:00:00Z --out gilead.rmcdelta
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime


class Command(BaseCommand):
    help = "Package recently-changed tenant records into a signed delta bundle for edge->operator sync."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug.")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (alternative to --slug).")
        parser.add_argument(
            "--since",
            default="",
            help="ISO-8601 cursor; only records changed strictly after this are included. Omit to include all.",
        )
        parser.add_argument(
            "--entities",
            default="",
            help="Comma-separated entity types to include (default: all supported).",
        )
        parser.add_argument("--out", required=True, help="Destination delta-bundle path.")
        parser.add_argument("--device-id", dest="device_id", default="edge", help="Edge/device id stamped in the bundle header.")

    def handle(self, *args, **options):
        from apps.api.sync_services import _get_entity_config  # SOT: (model, allowed-field set) per entity
        from apps.schools.models import School
        from apps.sync_engine.delta_bundle import export_delta_bundle

        slug = (options.get("slug") or "").strip()
        school_id = (options.get("school_id") or "").strip()
        if not slug and not school_id:
            raise CommandError("Provide --slug or --school-id.")
        school = (
            School.objects.filter(slug=slug).first()
            if slug
            else School.objects.filter(pk=school_id).first()
        )
        if school is None:
            raise CommandError(f"School not found ({slug or school_id}).")

        since = None
        raw_since = (options.get("since") or "").strip()
        if raw_since:
            since = parse_datetime(raw_since)
            if since is None:
                raise CommandError(f"Could not parse --since {raw_since!r} (use ISO-8601).")

        config = _get_entity_config()
        want = {e.strip().lower() for e in (options.get("entities") or "").split(",") if e.strip()}
        unknown = want - set(config)
        if unknown:
            raise CommandError(f"Unknown --entities: {sorted(unknown)}. Supported: {sorted(config)}.")

        rows: list[dict] = []
        counts: dict[str, int] = {}
        high_water = None
        for entity_type, (model, allowed) in config.items():
            if want and entity_type not in want:
                continue
            qs = model._default_manager.filter(school=school)  # school= is the tenant-isolation kwarg
            if since is not None:
                qs = qs.filter(updated_at__gt=since)
            n = 0
            for instance in qs.order_by("updated_at").iterator():
                changes = {f: getattr(instance, f) for f in sorted(allowed) if hasattr(instance, f)}
                updated_at = getattr(instance, "updated_at", None)
                rows.append(
                    {
                        "entity_type": entity_type,
                        "id": instance.pk,
                        "changes": changes,
                        "updated_at": updated_at.isoformat() if updated_at else None,
                    }
                )
                if updated_at and (high_water is None or updated_at > high_water):
                    high_water = updated_at
                n += 1
            if n:
                counts[entity_type] = n

        data = export_delta_bundle(
            school_id=str(school.id),
            rows=rows,
            device_id=(options.get("device_id") or "edge"),
        )
        out = Path(options["out"])
        out.write_bytes(data)

        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no changes"
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {out} ({len(rows)} row(s): {summary}); signed for {school.slug}.")
        )
        if high_water is not None:
            # Feed this back as --since on the next run so already-sent rows aren't re-posted.
            self.stdout.write(f"Next cursor (--since): {high_water.isoformat()}")
