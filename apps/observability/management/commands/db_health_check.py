"""
Lightweight DB health check for deploy pipeline (Phase I).

Run after migrate (or migrate_schemas --shared/--tenant) and before starting Gunicorn
so the orchestrator only routes traffic when the DB is ready.

§2.4 Raw SQL wrap: delegates to db_liveness.check_db_liveness() (single SELECT 1 in one place).

Usage: python manage.py db_health_check
Exit: 0 on success, 1 on failure.
"""

from django.core.management.base import BaseCommand

from apps.observability.db_liveness import check_db_liveness


class Command(BaseCommand):
    help = "Run one DB query to verify connectivity; exit 0 on success (for deploy health check)."

    def handle(self, *args, **options):
        result = check_db_liveness()
        if result.get("status") != "healthy":
            msg = result.get("error", "unknown")
            self.stdout.write(self.style.ERROR("db_health_check FAIL: %s" % msg))
            raise SystemExit(1)
        self.stdout.write("db_health_check OK")
