"""
Run tenant migrations one schema at a time; on failure log and continue.

Part 0 Migration Runner. Use when you want per-schema failure isolation:
if one tenant's migrations fail, others still run. See docs/MIGRATION_RUNNER_TENANT_SCHEMAS.md.
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db import DatabaseError, IntegrityError, OperationalError


class Command(BaseCommand):
    help = "Run migrations for each tenant schema; on failure log and continue to next."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only list tenants, do not run migrations.",
        )
        parser.add_argument("--verbosity", type=int, default=1)

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("PostgreSQL only. Skipping."))
            return
        if not getattr(settings, "USE_DJANGO_TENANTS", False):
            self.stdout.write(
                self.style.WARNING("USE_DJANGO_TENANTS is not enabled. Skipping.")
            )
            return
        try:
            from apps.customers.models import Client
            from django_tenants.utils import tenant_context
        except ImportError as e:
            self.stdout.write(self.style.ERROR("Import failed: %s" % e))
            return

        dry_run = options.get("dry_run", False)
        verbosity = options.get("verbosity", 1)
        failed = []
        ok = 0
        for client in Client.objects.all().order_by("id"):
            schema_name = getattr(client, "schema_name", None) or ""
            if not schema_name or schema_name == "public":
                continue
            if dry_run:
                self.stdout.write(
                    "Would migrate tenant: %s (schema %s)" % (client.name, schema_name)
                )
                ok += 1
                continue
            try:
                with tenant_context(client):
                    call_command("migrate", "--run-syncdb", verbosity=verbosity)
                ok += 1
                if verbosity >= 1:
                    self.stdout.write(
                        self.style.SUCCESS("OK: %s (%s)" % (client.name, schema_name))
                    )
            except (
                CommandError,
                DatabaseError,
                IntegrityError,
                OperationalError,
                OSError,
            ) as e:
                failed.append((schema_name, client.name, str(e)))
                self.stdout.write(
                    self.style.ERROR(
                        "FAILED: %s (%s) - %s" % (client.name, schema_name, e)
                    )
                )
        if failed:
            self.stdout.write(
                self.style.ERROR(
                    "Failed %s schema(s): %s" % (len(failed), [f[0] for f in failed])
                )
            )
        self.stdout.write(
            self.style.SUCCESS("Done. OK=%s Failed=%s" % (ok, len(failed)))
        )
