"""edge_autosync — zero-arg automatic edge<->cloud sync for THIS box's own school.

Unlike ``edge_sync_cycle`` (which needs an explicit ``--slug`` and is the operator's
manual / scheduled-by-slug tool), this resolves the box's sole school itself, so it is
the entry the boot entrypoint, the optional on-connectivity host hook, and a
broker-less cron all call with NO arguments.

Gated by ``RMC_EDGE_SYNC_ENABLED`` (a hard no-op on every other deployment) and never
raises on a normal offline cycle — the underlying runner records one EdgeSyncRun and
returns a result either way.

    python manage.py edge_autosync           # live push-up + pull-down
    python manage.py edge_autosync --dry     # no-write connectivity probe
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run one automatic edge<->cloud sync cycle for this box's school (no args; flag-gated, offline-safe)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry",
            action="store_true",
            help="No-write connectivity probe (counts pending + confirms reachability); applies nothing.",
        )

    def handle(self, *args, **options):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        mode = "dry" if options.get("dry") else "live"
        result = run_edge_sync_now(mode=mode)

        if not result.get("enabled", True):
            self.stdout.write("edge_autosync: RMC_EDGE_SYNC_ENABLED is off — no-op.")
            return
        if not result.get("ran"):
            self.stdout.write(
                self.style.WARNING(f"edge_autosync: skipped — {result.get('reason', 'no school')}.")
            )
            return

        msg = result.get("message") or ("ok" if result.get("ok") else "finished with errors")
        line = (
            f"edge_autosync ({result.get('mode', mode)}): pushed {result.get('pushed', 0)}, "
            f"pulled {result.get('pulled', 0)}, conflicts {result.get('conflicts', 0)} — {msg}"
        )
        self.stdout.write(self.style.SUCCESS(line) if result.get("ok") else line)
