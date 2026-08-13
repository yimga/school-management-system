"""One edge<->cloud sync cycle: push local changes UP, then pull cloud changes DOWN.

This is the single command the sovereign edge box schedules (cron / beat, e.g. every few
minutes). It is a thin, resilient orchestration over the tested per-direction commands
(``post_edge_outbox`` then ``pull_edge_inbox``), each with its OWN cursor file so the two
directions advance independently and idempotently.

GATED by ``settings.RMC_EDGE_SYNC_ENABLED``: on any deployment where the flag is off
(every ordinary cloud tenant) this is a pure no-op — nothing is pushed, pulled, or
reached over the network. Offline is handled by the sub-commands (they leave their cursor
put and simply retry next cycle), so a scheduled run during an outage is harmless.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run one edge<->cloud sync cycle (push up, then pull down). Flag-gated; offline-safe."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug.")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (alt to --slug).")
        parser.add_argument("--operator-base", dest="operator_base", default="", help="Operator base URL.")
        parser.add_argument("--token", default="", help="Edge bearer credential (default: env RMC_EDGE_CREDENTIAL).")
        parser.add_argument("--push-cursor-file", dest="push_cursor_file", default="", help="Push (outbox) cursor file.")
        parser.add_argument("--pull-cursor-file", dest="pull_cursor_file", default="", help="Pull (inbox) cursor file.")
        parser.add_argument("--entities", default="", help="Comma-separated entity filter (default: all supported).")
        parser.add_argument("--as-user", dest="as_user", default="", help="Local principal to apply pulled rows as.")
        parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds.")

    def handle(self, *args, **options):
        if not getattr(settings, "RMC_EDGE_SYNC_ENABLED", False):
            self.stdout.write(
                "RMC_EDGE_SYNC_ENABLED is off — edge sync cycle is a no-op on this deployment."
            )
            return

        slug = (options.get("slug") or "").strip()
        school_id = (options.get("school_id") or "").strip()
        if not slug and not school_id:
            raise CommandError("Provide --slug or --school-id.")

        common = {
            "slug": slug,
            "school_id": school_id,
            "operator_base": (options.get("operator_base") or "").strip(),
            "token": (options.get("token") or "").strip(),
            "entities": (options.get("entities") or "").strip(),
            "timeout": float(options.get("timeout") or 30.0),
        }

        # 1) PUSH local changes up. A rejection/failure is reported but does NOT abort the
        #    pull — the two directions are independent, and each leaves its cursor put on
        #    failure so nothing is lost.
        self.stdout.write("edge-sync: push …")
        try:
            call_command(
                "post_edge_outbox",
                cursor_file=(options.get("push_cursor_file") or "").strip(),
                **common,
            )
        except CommandError as exc:
            self.stderr.write(self.style.WARNING(f"edge-sync push failed: {exc}"))

        # 2) PULL cloud changes down.
        self.stdout.write("edge-sync: pull …")
        try:
            call_command(
                "pull_edge_inbox",
                cursor_file=(options.get("pull_cursor_file") or "").strip(),
                as_user=(options.get("as_user") or "").strip(),
                **common,
            )
        except CommandError as exc:
            self.stderr.write(self.style.WARNING(f"edge-sync pull failed: {exc}"))

        self.stdout.write(self.style.SUCCESS("edge-sync: cycle complete."))
