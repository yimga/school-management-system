"""Ping Celery workers (inspect.ping) for deploy / Render shell proof.

Exit codes:
  0 — soft-OK (no broker / eager) OR at least one worker answered
  1 — broker configured and no workers responded (or ping errored)

Usage:
  python manage.py ping_celery_workers
  python manage.py ping_celery_workers --strict   # fail even when requirement disabled
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Ping Celery workers via inspect.ping (broker-up / worker-alive proof)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 on degraded even if HEALTHZ_REQUIRE_CELERY_WORKERS is off.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        from apps.observability.views import _check_celery_workers

        result = _check_celery_workers()
        status = result.get("status")
        self.stdout.write(f"celery_workers status={status} detail={result}")

        if status == "unavailable":
            self.stdout.write(self.style.WARNING("ping_celery_workers SOFT: broker not configured"))
            return

        if status == "ok":
            workers = result.get("workers") or []
            self.stdout.write(self.style.SUCCESS(f"ping_celery_workers OK: {workers}"))
            return

        require = bool(getattr(settings, "HEALTHZ_REQUIRE_CELERY_WORKERS", True))
        if options.get("strict") or require:
            self.stdout.write(self.style.ERROR("ping_celery_workers FAIL: no live workers"))
            raise SystemExit(1)
        self.stdout.write(
            self.style.WARNING(
                "ping_celery_workers WARN: degraded but HEALTHZ_REQUIRE_CELERY_WORKERS off"
            )
        )
