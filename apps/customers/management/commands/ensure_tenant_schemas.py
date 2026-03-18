"""
Create any missing PostgreSQL schemas for django-tenants Clients.

When Clients are created inside a migration (e.g. customers.0003), django-tenants'
auto_create_schema may not run, so migrate_schemas --tenant fails with
"no schema has been selected to create in". Run this after migrate_schemas --shared
and before migrate_schemas --tenant to create missing schemas.

§2.4 Raw SQL wrap: delegates to customers.repositories.schema_provisioning_repository.

Usage: python manage.py ensure_tenant_schemas [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.db import connection

from apps.customers.repositories.schema_provisioning_repository import (
    create_schema_if_not_exists,
    schema_exists,
)


class Command(BaseCommand):
    help = "Create missing PostgreSQL schemas for all Clients (so migrate_schemas --tenant can run)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Only print what would be created."
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("PostgreSQL only. Skipping."))
            return
        from django.conf import settings

        if not getattr(settings, "USE_DJANGO_TENANTS", False):
            return
        try:
            from apps.customers.models import Client
        except ImportError:
            self.stdout.write(
                self.style.WARNING("customers.Client not available. Skipping.")
            )
            return

        dry_run = options.get("dry_run", False)
        created = 0
        for client in Client.objects.all().order_by("id"):
            schema_name = (getattr(client, "schema_name", None) or "").strip()
            if not schema_name:
                continue
            if schema_exists(schema_name):
                continue
            if dry_run:
                self.stdout.write(
                    "Would create schema: %s (Client %s)" % (schema_name, client.name)
                )
            else:
                create_schema_if_not_exists(schema_name)
                self.stdout.write("Created schema: %s" % schema_name)
            created += 1
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    "Done. Created or would create %s schema(s)." % created
                )
            )
