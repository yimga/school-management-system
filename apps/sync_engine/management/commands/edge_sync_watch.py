"""Long-poll the cloud and sync the instant something changes (G6).

The appliance sits behind NAT, so the cloud can never call it. Every transfer is
box-initiated, which makes cloud->box latency equal to the polling cadence - and the
adaptive cadence deliberately BACKS OFF on a quiet school, so an idle box can sit minutes
behind. This command closes that to about a second by holding one ordinary HTTP request
open against ``/api/sync/changes/`` and running a cycle the moment the cloud answers.

WHY A DEDICATED PROCESS AND NOT THE BEAT TASK. A long-poll blocks for up to 25 seconds by
design. Doing that inside the Celery beat tick would occupy a worker that other periodic
work needs, and a beat schedule cannot express "start again immediately". A small
long-running watcher is the honest shape for this pattern.

IT IS PURELY AN ACCELERATOR. It carries no data and moves no cursor: it only decides WHEN
to call the same ``run_sync_cycle`` everything else calls. So the existing cadence remains
a complete fallback - stop this command and the box keeps converging exactly as before,
just later. Every failure mode here degrades to that: an unsupported feed, an unreachable
cloud, a 4xx, all fall back to sleeping for the cadence interval and cycling anyway.

    python manage.py edge_sync_watch                # run until stopped
    python manage.py edge_sync_watch --once         # one hold, for a smoke test
    python manage.py edge_sync_watch --max-cycles 5 # bounded, for CI
"""
from __future__ import annotations

import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse
from apps.sync_engine.cloud_endpoints import CLOUD_SYNC_PATHS

# Never hammer the cloud when it is unhappy. Both are seconds.
_ERROR_BACKOFF_SECONDS = 30  # magic-number-allow: pause after a failed hold
_IDLE_FLOOR_SECONDS = 1  # magic-number-allow: minimum gap between cycles


class Command(BaseCommand):
    help = "Long-poll the cloud changes feed and run a sync cycle as soon as it answers."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="School id or subdomain (default: the only one)")
        parser.add_argument("--once", action="store_true", help="Do a single hold and exit")
        parser.add_argument("--max-cycles", type=int, default=0, help="Stop after N cycles (0 = unlimited)")
        parser.add_argument("--wait", type=int, default=0, help="Seconds to hold (default: the cloud's max)")

    def handle(self, *args, **options):
        from apps.sync_engine import edge_outbox
        from apps.sync_engine.sync_runner import run_sync_cycle

        if not getattr(settings, "RMC_EDGE_SYNC_ENABLED", False):
            self.stdout.write(self.style.WARNING(
                "RMC_EDGE_SYNC_ENABLED is off; the watcher would drive nothing. Exiting."
            ))
            return

        school = self._resolve_school(options.get("school") or "")
        if school is None:
            self.stderr.write(self.style.ERROR("no school resolved on this box"))
            return

        base = self._operator_base()
        token = self._edge_token()
        endpoint = base + self._path(
            "api:sync-changes-feed", CLOUD_SYNC_PATHS["api:sync-changes-feed"]
        )
        wait = int(options.get("wait") or 0) or int(
            getattr(settings, "RMC_SYNC_CHANGES_FEED_MAX_WAIT_SECONDS", 25)
        )

        stopping = {"now": False}

        def _stop(_signum, _frame):
            # A watcher that ignores SIGTERM is a watcher an operator has to kill -9,
            # which is how a cycle gets interrupted between apply and cursor advance.
            stopping["now"] = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _stop)
            except (ValueError, OSError):  # pragma: no cover - not the main thread
                pass

        cycles = 0
        max_cycles = int(options.get("max_cycles") or 0)
        self.stdout.write(f"watching {endpoint} (hold {wait}s)")
        while not stopping["now"]:
            changed, supported, reason = self._hold(edge_outbox, endpoint, token, wait, school)
            if reason:
                self.stderr.write(self.style.WARNING(reason))
            if not supported:
                self.stdout.write(
                    "the cloud does not run the changes feed; falling back to the cadence"
                )
            if changed:
                result = run_sync_cycle(school, mode="live")
                cycles += 1
                self.stdout.write(
                    f"cycle {cycles}: ok={result.get('ok')} "
                    f"pulled={result.get('pulled')} pushed={result.get('pushed')} "
                    f"deleted={result.get('deleted')} — {result.get('message') or ''}"
                )
            if options.get("once") or (max_cycles and cycles >= max_cycles):
                break
            # A floor between cycles, so a cloud that answers "changed" instantly (because
            # the box's own push is what changed it) cannot spin this into a busy loop.
            time.sleep(_ERROR_BACKOFF_SECONDS if reason else _IDLE_FLOOR_SECONDS)
        self.stdout.write(self.style.SUCCESS(f"watcher stopped after {cycles} cycle(s)"))

    # ---------------------------------------------------------------- helpers
    def _hold(self, edge_outbox, endpoint, token, wait, school):
        """``(changed, supported, error_reason)``. Never raises."""
        from apps.sync_engine.models import EdgeSyncCursor, get_sync_cursor

        since = get_sync_cursor(school, EdgeSyncCursor.PULL)
        try:
            status, payload = edge_outbox.wait_for_changes(
                endpoint, token, since=since, wait=wait, timeout=wait + 15
            )
        except Exception as exc:  # noqa: BLE001 — offline is the normal case out here
            # Cycle anyway: the box may still have local changes to push, and the ordinary
            # cycle is what records the unreachable-cloud outcome for the Sync Center.
            return True, True, f"changes feed unreachable ({exc}); falling back to a cycle"
        if status != 200:
            return True, True, f"changes feed returned HTTP {status}; falling back to a cycle"
        supported = bool(payload.get("supported", True))
        return bool(payload.get("changed")), supported, ""

    def _resolve_school(self, hint):
        from apps.schools.models import School

        qs = School.objects.all()
        if hint:
            found = qs.filter(subdomain=hint).first() or qs.filter(slug=hint).first()
            if found is None:
                found = qs.filter(pk=hint).first() if hint.isdigit() or "-" in hint else None
            return found
        # A sovereign box is single-tenant by construction, so "the only school" is the
        # right default; refusing to guess when there are several is safer than picking.
        return qs.first() if qs.count() == 1 else None

    @staticmethod
    def _operator_base():
        base = (getattr(settings, "RMC_EDGE_OPERATOR_BASE", "") or "").strip()
        if not base:
            base = (getattr(settings, "RMC_HUB_BASE_URL", "") or "").strip()
        return base.rstrip("/")

    @staticmethod
    def _edge_token():
        import os

        return (os.getenv("RMC_EDGE_CREDENTIAL") or "").strip()

    @staticmethod
    def _path(url_name, fallback):
        try:
            return reverse(url_name)
        except NoReverseMatch:
            return fallback
