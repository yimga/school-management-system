"""
Single entry point to run migrations for all tenant schemas.

1. Ensures every Client has a PostgreSQL schema (ensure_tenant_schemas).
2. Runs migrate_schemas --tenant to apply all TENANT_APPS migrations in each schema.

Use for deployment or after adding migrations: one command to bring all tenant
schemas up to date. See docs/MASTER_TABLE_LIST.md for the canonical table list.
"""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "Ensure all tenant schemas exist, then run migrate_schemas --tenant. "
        "Single entry point for 'run migrations for all tenant schemas'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            dest="no_input",
            help="Do not prompt for input (e.g. for CI/deploy).",
        )
        parser.add_argument(
            "--skip-ensure-schemas",
            action="store_true",
            help="Skip ensure_tenant_schemas; only run migrate_schemas --tenant.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("PostgreSQL only. Skipping."))
            return
        if not getattr(settings, "USE_DJANGO_TENANTS", False):
            self.stdout.write(self.style.WARNING("USE_DJANGO_TENANTS is not enabled. Skipping."))
            return

        no_input = options.get("no_input", False)
        skip_ensure = options.get("skip_ensure_schemas", False)

        if not skip_ensure:
            self.stdout.write("Ensuring tenant schemas exist...")
            call_command("ensure_tenant_schemas", verbosity=options.get("verbosity", 1))
        self.stdout.write("Running migrate_schemas --tenant...")
        call_command(
            "migrate_schemas",
            "--tenant",
            no_input=no_input,
            verbosity=options.get("verbosity", 1),
        )
        self.stdout.write(self.style.SUCCESS("Done."))
