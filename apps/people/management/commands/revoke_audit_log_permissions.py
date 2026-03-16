"""
Revoke UPDATE and DELETE on audit_log in each tenant schema (immutable audit trail).

Part 4.6. Run after tenant migrations so the app role can only INSERT into audit_log.
§2.4 Raw SQL wrap: delegates to people.repositories.audit_repository.

PostgreSQL only. Use --dry-run to print SQL without executing.

  python manage.py revoke_audit_log_permissions
  python manage.py revoke_audit_log_permissions --schema my_tenant_schema
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import DatabaseError, OperationalError, ProgrammingError

from apps.people.repositories.audit_repository import revoke_audit_log_mutations, set_search_path
from apps.platform_runtime.structured_logging import log_exception_with_context

# Typed exceptions for revoke_audit_log DDL (per-schema loop).
_REVOKE_AUDIT_LOG_PERMISSIONS_ERRORS: tuple[type[BaseException], ...] = (
    DatabaseError,
    OperationalError,
    ProgrammingError,
)


class Command(BaseCommand):
    help = "Revoke UPDATE/DELETE on audit_log in each tenant schema (PostgreSQL)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Single schema to run in (default: all tenant schemas).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Print SQL only, do not execute.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.ERROR("PostgreSQL only."))
            return
        single_schema = options.get("schema")
        dry_run = options.get("dry_run", False)

        if single_schema:
            schemas = [(single_schema, single_schema)]
        else:
            try:
                from apps.customers.models import Client
            except ImportError:
                self.stdout.write(self.style.ERROR("django-tenants required. Use --schema."))
                return
            schemas = [
                (getattr(c, "schema_name", ""), getattr(c, "name", c.schema_name))
                for c in Client.objects.exclude(schema_name="public").filter(schema_name__isnull=False).order_by("id")
            ]
            schemas = [(s, n) for s, n in schemas if s]

        if not schemas:
            self.stdout.write(self.style.WARNING("No tenant schemas found."))
            return

        for schema_name, label in schemas:
            if dry_run:
                self.stdout.write(f"Would run: SET search_path TO {schema_name}; REVOKE UPDATE, DELETE ON audit_log FROM CURRENT_USER;")
                continue
            try:
                with connection.cursor() as cursor:
                    set_search_path(cursor, schema_name)
                    revoke_audit_log_mutations(cursor)
                self.stdout.write(self.style.SUCCESS("OK %s (%s)" % (label, schema_name)))
            except _REVOKE_AUDIT_LOG_PERMISSIONS_ERRORS as e:
                log_exception_with_context(
                    "revoke_audit_log_permissions: failed for schema",
                    school_id=None,
                    extra={"schema_name": schema_name, "label": label, "error": str(e)},
                )
                self.stdout.write(self.style.ERROR("FAILED %s: %s" % (schema_name, e)))
