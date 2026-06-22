"""Detect AND heal tenant-schema drift — missing TABLES and missing COLUMNS.

The comprehensive operator companion to ``detect_tenant_table_drift`` (read-only,
tables only) and the per-app ``schema_repair`` heals. It introspects the live
model registry against the actual DB and converges a tenant schema that missed
(or fake-applied) migrations — including the COLUMN drift the table-only detector
cannot see (e.g. ``finance_notification.dismissed_at`` from a recorded-but-not-
landed ``AddField``, which 500s the notification bell on every page).

    python manage.py heal_tenant_schema_drift                # report ALL schemas (dry-run)
    python manage.py heal_tenant_schema_drift --schema=acme  # report one schema
    python manage.py heal_tenant_schema_drift --apply        # HEAL all schemas
    python manage.py heal_tenant_schema_drift --schema=acme --apply

Dry-run by default (read-only). ``--apply`` performs idempotent, best-effort DDL:
each table/column is created in its own savepoint, so a single failure (e.g. a
NOT NULL add on a populated table) is logged and skipped and never aborts the
rest or another schema. Exit code 1 when drift remains (so cron/CI can trip).
"""

from __future__ import annotations

from contextlib import nullcontext

from django.core.management.base import BaseCommand
from django.db import connection

from apps.schools.tenant_schema_guard import (
    _managed_tenant_models,
    ensure_models_columns,
    ensure_models_tables,
    missing_tenant_columns,
    missing_tenant_tables,
)


class Command(BaseCommand):
    help = "Detect and (with --apply) heal missing tenant tables AND columns."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            dest="schema",
            default=None,
            help="Only this schema name (default: every tenant schema).",
        )
        parser.add_argument(
            "--apply",
            dest="apply",
            action="store_true",
            help="Perform the heal (default: report only / dry-run).",
        )

    def handle(self, *args, **options):
        apply = bool(options.get("apply"))
        drift_remains = False

        for schema_name, enter in self._iter_schemas(options.get("schema")):
            with enter():
                missing_tables = missing_tenant_tables()
                missing_columns = missing_tenant_columns()

                if not missing_tables and not missing_columns:
                    self.stdout.write(self.style.SUCCESS(f"[{schema_name}] clean"))
                    continue

                self.stdout.write(
                    self.style.WARNING(
                        f"[{schema_name}] missing {len(missing_tables)} table(s), "
                        f"{len(missing_columns)} column(s)"
                    )
                )
                for app, model, table in missing_tables:
                    self.stdout.write(f"    table   {app}.{model} ({table})")
                for app, model, table, column in missing_columns:
                    self.stdout.write(f"    column  {table}.{column}")

                if not apply:
                    drift_remains = True
                    continue

                models = list(_managed_tenant_models())
                with connection.schema_editor() as editor:
                    created = ensure_models_tables(editor, models)
                    added = ensure_models_columns(editor, models)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[{schema_name}] healed {len(created)} table(s), "
                        f"{len(added)} column(s)"
                    )
                )

                left_tables = missing_tenant_tables()
                left_columns = missing_tenant_columns()
                if left_tables or left_columns:
                    drift_remains = True
                    self.stdout.write(
                        self.style.ERROR(
                            f"[{schema_name}] STILL missing "
                            f"{len(left_tables)} table(s), {len(left_columns)} "
                            f"column(s) — manual review (see logs)"
                        )
                    )

        if drift_remains:
            if not apply:
                self.stdout.write(
                    self.style.WARNING("\nDrift found. Re-run with --apply to heal.")
                )
            raise SystemExit(1)

    def _iter_schemas(self, only_schema):
        """Yield (schema_name, context-manager factory) for each tenant schema.

        Under shared-DB / RLS mode (no django-tenants) there is a single schema,
        reported as ``public`` with a no-op context.
        """
        try:
            from django_tenants.utils import get_tenant_model, schema_context
        except ImportError:
            yield ("public", nullcontext)
            return

        qs = get_tenant_model().objects.exclude(schema_name="public")
        if only_schema:
            qs = qs.filter(schema_name=only_schema)
        for client in qs.order_by("schema_name"):
            name = client.schema_name
            yield (name, lambda n=name: schema_context(n))
