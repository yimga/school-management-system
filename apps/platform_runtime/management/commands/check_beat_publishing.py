"""Is Celery beat actually PUBLISHING, or merely running?

    python manage.py check_beat_publishing          # exit 0 healthy, 1 stale
    python manage.py check_beat_publishing --json

Written to be a container healthcheck for the ``beat`` service, which has no HTTP
surface and no ``inspect`` protocol of its own. Checking that the process is up
would prove nothing: the failure this exists for is a beat that is up, attached to
the broker, and publishing NOTHING — measured on a sovereign box on 2026-08-20,
where the broker held no ``celery`` queue at all because no task had ever been
enqueued, while the beat container sat there looking perfectly healthy.

The canary is ``schools.resume_stuck_provisions`` — already in
``CELERY_BEAT_SCHEDULE`` at 120s, and already the signal the application reads to
decide whether the in-process scheduler must take over. Reusing it keeps one
definition of "beat is alive" instead of inventing a second one that can disagree
with the first.

Exit codes are the interface: 0 healthy, 1 stale. Nothing is written except the
durable watch anchor that ``celery_beat_appears_alive`` creates on first look.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exit non-zero when Celery beat has not published its canary recently."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")

    def handle(self, *args, **options):
        from apps.platform_runtime.periodic import (
            BEAT_LIVENESS_CANARY_JOB,
            celery_beat_appears_alive,
            celery_beat_liveness_threshold_seconds,
            inprocess_scheduler_enabled,
        )

        alive = bool(celery_beat_appears_alive())
        payload = {
            "ok": alive,
            "canary": BEAT_LIVENESS_CANARY_JOB,
            "threshold_seconds": celery_beat_liveness_threshold_seconds(),
            # Reported so an operator reading a failed healthcheck can tell the
            # difference between "beat is down and the heal has it" (degraded but
            # running) and "beat is down and nothing else is scheduled either"
            # (everything periodic on this deployment has stopped).
            "inprocess_scheduler": bool(inprocess_scheduler_enabled()),
        }

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2))
        elif alive:
            self.stdout.write(self.style.SUCCESS(f"beat is publishing ({BEAT_LIVENESS_CANARY_JOB} fresh)"))
        else:
            takeover = (
                "the in-process scheduler has taken over"
                if payload["inprocess_scheduler"]
                else "and the in-process scheduler is OFF — nothing is running periodic jobs"
            )
            self.stdout.write(
                self.style.ERROR(
                    f"beat has not published {BEAT_LIVENESS_CANARY_JOB} within "
                    f"{payload['threshold_seconds']:.0f}s — {takeover}"
                )
            )

        if not alive:
            raise SystemExit(1)
