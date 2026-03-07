"""
Attach audit triggers to additional tenant tables (e.g. finance_invoice, finance_payment).

Part 4.6. Migration 0037 already attaches to people_studentprofile and people_teacherprofile.
Use this command to add the same trigger to other tables without a new migration.

  python manage.py attach_audit_triggers --tables finance_invoice finance_payment
  python manage.py attach_audit_triggers --tables finance_invoice --schema my_tenant_schema

Runs in each tenant schema (or the given schema). PostgreSQL only.
"""
from django.core.management.base import BaseCommand
from django.db import connection

# Must match migration 0037 REDACT_KEYS (PII masking).
REDACT_KEYS = [
    "password", "password_hash", "secret", "token", "api_key",
    "card_last4", "card_number", "ssn", "social_security",
]


def _create_trigger_function(cursor):
    redact_keys_sql = "ARRAY[" + ", ".join(repr(k) for k in REDACT_KEYS) + "]::text[]"
    cursor.execute(
        """
        CREATE OR REPLACE FUNCTION audit_trigger_fn()
        RETURNS TRIGGER AS $$
        DECLARE
          old_json jsonb;
          new_json jsonb;
          action text;
          tbl text;
          rec_id text;
          redact_keys text[] := """
        + redact_keys_sql
        + """;
        BEGIN
          tbl := TG_TABLE_NAME;
          action := TG_OP;
          IF TG_OP = 'DELETE' THEN
            old_json := to_jsonb(OLD) - redact_keys;
            new_json := NULL;
            rec_id := (OLD).id::text;
          ELSIF TG_OP = 'UPDATE' THEN
            old_json := to_jsonb(OLD) - redact_keys;
            new_json := to_jsonb(NEW) - redact_keys;
            rec_id := (NEW).id::text;
          ELSE
            old_json := NULL;
            new_json := to_jsonb(NEW) - redact_keys;
            rec_id := (NEW).id::text;
          END IF;
          INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, changed_at)
          VALUES (tbl, rec_id, action, old_json, new_json, now());
          IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def _attach_to_table(cursor, table_name):
    trigger_name = "audit_" + table_name.replace(".", "_")
    # Use identifier quoting for trigger/table names (safe for standard names).
    cursor.execute(
        'DROP TRIGGER IF EXISTS "%s" ON "%s"' % (trigger_name.replace('"', '""'), table_name.replace('"', '""'))
    )
    cursor.execute(
        'CREATE TRIGGER "%s" AFTER INSERT OR UPDATE OR DELETE ON "%s" '
        'FOR EACH ROW EXECUTE PROCEDURE audit_trigger_fn()'
        % (trigger_name.replace('"', '""'), table_name.replace('"', '""'))
    )


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
        parser.add_argument("--dry-run", action="store_true", help="Only list what would be done.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.ERROR("PostgreSQL only."))
            return
        tables = [t.strip() for t in options["tables"] if t.strip()]
        if not tables:
            self.stdout.write(self.style.ERROR("Provide at least one table with --tables."))
            return
        dry_run = options.get("dry_run", False)
        single_schema = options.get("schema")

        if single_schema:
            if dry_run:
                self.stdout.write("Would attach in schema %s: %s" % (single_schema, tables))
            else:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SET search_path TO %s", [single_schema])
                        _create_trigger_function(cursor)
                        for table in tables:
                            _attach_to_table(cursor, table)
                    self.stdout.write(self.style.SUCCESS("OK %s: %s" % (single_schema, tables)))
                except Exception as e:
                    self.stdout.write(self.style.ERROR("FAILED %s: %s" % (single_schema, e)))
            return

        try:
            from apps.customers.models import Client
            from django_tenants.utils import tenant_context
        except ImportError:
            self.stdout.write(self.style.ERROR("django-tenants required for all-tenant run. Use --schema."))
            return
        clients = list(Client.objects.exclude(schema_name="public").filter(schema_name__isnull=False).order_by("id"))
        if not clients:
            self.stdout.write(self.style.WARNING("No tenant schemas found."))
            return
        for client in clients:
            schema_name = getattr(client, "schema_name", "")
            label = getattr(client, "name", schema_name)
            if dry_run:
                self.stdout.write("Would attach to %s (%s): %s" % (label, schema_name, tables))
                continue
            try:
                with tenant_context(client):
                    with connection.cursor() as cursor:
                        _create_trigger_function(cursor)
                        for table in tables:
                            _attach_to_table(cursor, table)
                self.stdout.write(self.style.SUCCESS("OK %s: %s" % (label, tables)))
            except Exception as e:
                self.stdout.write(self.style.ERROR("FAILED %s: %s" % (label, e)))
