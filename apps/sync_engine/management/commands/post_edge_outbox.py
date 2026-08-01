"""Post the edge box's changed records UP to the operator (Tier 3 Slice 3, box side).

Edge-initiated / outbound-only: the box builds a signed delta bundle of everything
changed since a cursor and POSTs it to the operator's receiver with its machine
credential. Queue-and-forward is by design idempotent — the cursor advances ONLY on a
successful post, so an offline run leaves the cursor put and the next run simply
re-sends the same window (apply_changes is last-writer-wins by ``updated_at``, so a
re-send is harmless). The failed bundle is also written to the outbox dir for manual
inspection/replay.

    python manage.py post_edge_outbox --slug gilead-tech \
        --operator-base https://gilead-tech.runmycampus.com \
        --cursor-file var/edge-sync.cursor   # token from env RMC_EDGE_CREDENTIAL

Reachability: the box calls OUT to the operator, so the operator never needs to reach
a box behind a private LAN (no inbound tunnel). Downstream (operator->box) sync is a
separate poll, out of scope for this command.
"""
from __future__ import annotations

import os
import secrets
import urllib.error
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.urls import NoReverseMatch, reverse
from django.utils.dateparse import parse_datetime


class Command(BaseCommand):
    help = "Build a delta bundle of recent changes and POST it to the operator (queue-and-forward)."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug.")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (alternative to --slug).")
        parser.add_argument("--endpoint", default="", help="Full URL of the operator receiver (overrides --operator-base).")
        parser.add_argument("--operator-base", dest="operator_base", default="", help="Operator base URL; the receiver path is appended.")
        parser.add_argument("--token", default="", help="Edge bearer credential (default: env RMC_EDGE_CREDENTIAL).")
        parser.add_argument("--since", default="", help="ISO-8601 cursor override (default: read --cursor-file).")
        parser.add_argument("--cursor-file", dest="cursor_file", default="", help="Path to read/persist the sync cursor.")
        parser.add_argument("--outbox-dir", dest="outbox_dir", default="", help="Dir to drop bundles that failed to send (default: <cwd>/var/edge-outbox).")
        parser.add_argument("--entities", default="", help="Comma-separated entity types (default: all supported).")
        parser.add_argument("--device-id", dest="device_id", default="edge", help="Device id stamped in the bundle header.")
        parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds.")
        parser.add_argument("--allow-empty", action="store_true", help="POST even when there are no changes.")

    def handle(self, *args, **options):
        from apps.schools.models import School
        from apps.sync_engine import edge_outbox

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

        token = (options.get("token") or os.getenv("RMC_EDGE_CREDENTIAL") or "").strip()
        if not token:
            raise CommandError("No credential: pass --token or set RMC_EDGE_CREDENTIAL.")

        endpoint = (options.get("endpoint") or "").strip()
        if not endpoint:
            base = (options.get("operator_base") or "").strip()
            if not base:
                raise CommandError("Provide --endpoint or --operator-base.")
            try:
                path = reverse("api:sync-bundle-upload")
            except NoReverseMatch:
                path = "/api/v1/sync/bundle/upload/"
            endpoint = base.rstrip("/") + path

        cursor_file = (options.get("cursor_file") or "").strip()
        raw_since = (options.get("since") or "").strip()
        if not raw_since and cursor_file and Path(cursor_file).exists():
            raw_since = Path(cursor_file).read_text(encoding="utf-8").strip()
        since = None
        if raw_since:
            since = parse_datetime(raw_since)
            if since is None:
                raise CommandError(f"Could not parse cursor {raw_since!r} (use ISO-8601).")

        entities = [e.strip().lower() for e in (options.get("entities") or "").split(",") if e.strip()]
        try:
            data, meta = edge_outbox.build_edge_delta_bundle(
                school, since=since, entities=entities, device_id=(options.get("device_id") or "edge")
            )
        except ValueError as exc:
            raise CommandError(str(exc).replace("unknown_entities:", "Unknown --entities: "))

        if meta["row_count"] == 0 and not options.get("allow_empty"):
            self.stdout.write("Nothing changed since the cursor — nothing to send.")
            return

        outbox_dir = Path(options.get("outbox_dir") or (Path.cwd() / "var" / "edge-outbox"))

        try:
            status, body = edge_outbox.post_bundle(endpoint, token, data, timeout=float(options.get("timeout") or 30.0))
        except (urllib.error.URLError, OSError) as exc:
            # Offline / unreachable: cursor stays put so the next run re-sends this window.
            queued = self._drop(outbox_dir, data)
            self.stderr.write(self.style.WARNING(
                f"Operator unreachable ({exc}); cursor NOT advanced (will re-send next run). "
                f"Bundle saved for manual replay: {queued}"
            ))
            return

        if status == 200 and body.get("ok"):
            applied = body.get("applied", 0)
            conflicts = body.get("conflicts", 0)
            self.stdout.write(self.style.SUCCESS(
                f"Posted {meta['row_count']} row(s) -> operator applied {applied}, conflicts {conflicts}."
            ))
            if cursor_file and meta["high_water_iso"]:
                Path(cursor_file).write_text(meta["high_water_iso"], encoding="utf-8")
                self.stdout.write(f"Cursor advanced -> {meta['high_water_iso']}")
            return

        # A real HTTP response but a rejection (bad signature, school mismatch, forbidden,
        # 4xx/5xx): do NOT advance the cursor; keep the bundle for inspection.
        queued = self._drop(outbox_dir, data)
        raise CommandError(
            f"Operator rejected the bundle (HTTP {status}): {body}. "
            f"Cursor NOT advanced. Bundle saved: {queued}"
        )

    @staticmethod
    def _drop(outbox_dir: Path, data: bytes) -> Path:
        outbox_dir.mkdir(parents=True, exist_ok=True)
        target = outbox_dir / f"edge-{secrets.token_hex(6)}.rmcdelta"
        target.write_bytes(data)
        return target
