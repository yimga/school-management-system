"""
Lightweight DB health check for deploy pipeline (Phase I).

Run after migrate (or migrate_schemas --shared/--tenant) and before starting Gunicorn
so the orchestrator only routes traffic when the DB is ready.

Usage: python manage.py db_health_check
Exit: 0 on success, 1 on failure.
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Run one DB query to verify connectivity; exit 0 on success (for deploy health check)."

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            self.stdout.write("db_health_check OK")
        except Exception as e:
            self.stdout.write(self.style.ERROR("db_health_check FAIL: %s" % e))
            raise SystemExit(1)
