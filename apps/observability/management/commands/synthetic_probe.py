"""
Synthetic monitoring probe for SRE/observability (Section 25.4).

Runs lightweight checks (healthz, ready, optional DB) to simulate external monitoring.
Use in cron or scheduler for uptime/availability checks.

§2.4 Raw SQL wrap: --db check delegates to db_liveness.check_db_liveness() (single SELECT 1 in one place).

Usage:
  python manage.py synthetic_probe
  python manage.py synthetic_probe --db
  python manage.py synthetic_probe --db --ready
"""

from django.core.management.base import BaseCommand
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from apps.observability.db_liveness import check_db_liveness


class Command(BaseCommand):
    help = "Synthetic probe: healthz-style checks (optionally DB, ready) for SRE monitoring."

    def add_arguments(self, parser):
        parser.add_argument(
            "--db",
            action="store_true",
            help="Include DB connectivity check (same as db_health_check).",
        )
        parser.add_argument(
            "--ready",
            action="store_true",
            help="Resolve ready URL (no HTTP call; validates URL config).",
        )

    def handle(self, *args, **options):
        failed = []
        # 1) Logical "healthz": app is importable and manage.py runs
        self.stdout.write("synthetic_probe: healthz OK (process running)")

        if options["db"]:
            result = check_db_liveness()
            if result.get("status") != "healthy":
                failed.append("db: %s" % result.get("error", "unknown"))
            else:
                self.stdout.write("synthetic_probe: db OK")

        if options["ready"]:
            try:
                path = reverse("ready")
                self.stdout.write("synthetic_probe: ready path=%s OK" % path)
            except (NoReverseMatch, ImproperlyConfigured) as e:
                failed.append("ready: %s" % e)

        if failed:
            for f in failed:
                self.stdout.write(self.style.ERROR("synthetic_probe FAIL: %s" % f))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("synthetic_probe: all checks OK"))
