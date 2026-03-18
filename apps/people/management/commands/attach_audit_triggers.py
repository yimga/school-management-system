"""
Attach audit triggers to additional tenant tables (e.g. finance_invoice, finance_payment).

Part 4.6. Migration 0037 already attaches to people_studentprofile and people_teacherprofile.
Use this command to add the same trigger to other tables without a new migration.

§2.4 Raw SQL wrap: delegates to people.repositories.audit_repository.
§2.4 Broad except: replaced with typed _AUDIT_TRIGGER_ERRORS (DatabaseError, OperationalError, ProgrammingError).
§2.4 Structured logging: log_exception_with_context in both single-schema and per-tenant paths.

  python manage.py attach_audit_triggers --tables finance_invoice finance_payment
  python manage.py attach_audit_triggers --tables finance_invoice --schema my_tenant_schema

Runs in each tenant schema (or the given schema). PostgreSQL only.
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db import DatabaseError, OperationalError, ProgrammingError

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.people.repositories.audit_repository import (
    create_audit_trigger,
    create_audit_trigger_function,
    drop_audit_trigger,
    set_search_path,
)

# §2.4 Typed exceptions for trigger attach (cursor/DDL); allowlist 0.
_AUDIT_TRIGGER_ERRORS = (DatabaseError, OperationalError, ProgrammingError)


class Command(BaseCommand):
    help = "Attach audit triggers to additional tenant tables (PostgreSQL, per-tenant)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tables",
            nargs="+",
            required=True,
            help="Table names (e.g. finance_invoice finance_payment).",
        )
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Single schema to run in (default: run for all tenant schemas).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Only list what would be done."
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.ERROR("PostgreSQL only."))
            return
        tables = [t.strip() for t in options["tables"] if t.strip()]
        if not tables:
            self.stdout.write(
                self.style.ERROR("Provide at least one table with --tables.")
            )
            return
        dry_run = options.get("dry_run", False)
        single_schema = options.get("schema")

        if single_schema:
            if dry_run:
                self.stdout.write(
                    "Would attach in schema %s: %s" % (single_schema, tables)
                )
            else:
                try:
                    with connection.cursor() as cursor:
                        set_search_path(cursor, single_schema)
                        create_audit_trigger_function(cursor)
                        for table in tables:
                            drop_audit_trigger(cursor, table)
                            create_audit_trigger(cursor, table)
                    self.stdout.write(
                        self.style.SUCCESS("OK %s: %s" % (single_schema, tables))
                    )
                except _AUDIT_TRIGGER_ERRORS as e:
                    log_exception_with_context(
                        "attach_audit_triggers failed (single schema)",
                        school_id=None,
                        extra={
                            "schema": single_schema,
                            "tables": tables,
                            "error": str(e),
                        },
                    )
                    self.stdout.write(
                        self.style.ERROR("FAILED %s: %s" % (single_schema, e))
                    )
            return

        try:
            from apps.customers.models import Client
            from django_tenants.utils import tenant_context
        except ImportError:
            self.stdout.write(
                self.style.ERROR(
                    "django-tenants required for all-tenant run. Use --schema."
                )
            )
            return
        clients = list(
            Client.objects.exclude(schema_name="public")
            .filter(schema_name__isnull=False)
            .order_by("id")
        )
        if not clients:
            self.stdout.write(self.style.WARNING("No tenant schemas found."))
            return
        for client in clients:
            schema_name = getattr(client, "schema_name", "")
            label = getattr(client, "name", schema_name)
            if dry_run:
                self.stdout.write(
                    "Would attach to %s (%s): %s" % (label, schema_name, tables)
                )
                continue
            try:
                with tenant_context(client):
                    with connection.cursor() as cursor:
                        create_audit_trigger_function(cursor)
                        for table in tables:
                            drop_audit_trigger(cursor, table)
                            create_audit_trigger(cursor, table)
                self.stdout.write(self.style.SUCCESS("OK %s: %s" % (label, tables)))
            except _AUDIT_TRIGGER_ERRORS as e:
                log_exception_with_context(
                    "attach_audit_triggers failed (tenant)",
                    school_id=getattr(client, "id", None),
                    extra={
                        "schema_name": schema_name,
                        "label": label,
                        "tables": tables,
                        "error": str(e),
                    },
                )
                self.stdout.write(self.style.ERROR("FAILED %s: %s" % (label, e)))
