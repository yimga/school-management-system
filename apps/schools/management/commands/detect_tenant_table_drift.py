"""Report tenant schemas that are missing expected tenant-app tables.

READ-ONLY. The companion to the per-column schema_repair heals and the
ensure-exists heal migrations: surfaces the rarer "fake-applied CreateModel"
drift (migration recorded as applied but the table was never created), which
`migrate_schemas --tenant` skips and so would otherwise only show up as a 500.

    python manage.py detect_tenant_table_drift            # all tenant schemas
    python manage.py detect_tenant_table_drift --schema=acme
    python manage.py detect_tenant_table_drift --json

Exit code 1 when any drift is found, so it can gate CI / alert ops.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.schools.tenant_schema_guard import missing_tenant_tables


class Command(BaseCommand):
    help = "Report tenant schemas missing expected tenant-app tables (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            dest="schema",
            default=None,
            help="Check only this schema name (default: every tenant schema).",
        )
        parser.add_argument(
            "--json",
            dest="as_json",
            action="store_true",
            help="Emit machine-readable JSON instead of text.",
        )

    def handle(self, *args, **options):
        report = self._collect(options.get("schema"))

        if options.get("as_json"):
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            self._render_text(report)

        drift = any(rows for rows in report.values())
        if drift:
            # Non-zero so CI / cron alerting can trip on it.
            raise SystemExit(1)

    def _collect(self, only_schema):
        """Map schema_name -> [ "app.Model (db_table)", ... ] of missing tables."""
        try:
            from django_tenants.utils import get_tenant_model, schema_context

            using_tenants = True
        except ImportError:
            using_tenants = False

        report: dict[str, list[str]] = {}

        if not using_tenants:
            # Shared-DB / RLS mode: only the one (public) schema exists.
            report["public"] = self._fmt(missing_tenant_tables())
            return report

        tenant_model = get_tenant_model()
        qs = tenant_model.objects.exclude(schema_name="public")
        if only_schema:
            qs = qs.filter(schema_name=only_schema)

        for client in qs.order_by("schema_name"):
            with schema_context(client.schema_name):
                report[client.schema_name] = self._fmt(missing_tenant_tables())
        return report

    @staticmethod
    def _fmt(rows):
        return [f"{app}.{model} ({table})" for app, model, table in rows]

    def _render_text(self, report):
        if not report:
            self.stdout.write("No tenant schemas found.")
            return
        clean = True
        for schema_name, rows in sorted(report.items()):
            if not rows:
                continue
            clean = False
            self.stdout.write(
                self.style.ERROR(
                    f"[{schema_name}] missing {len(rows)} table(s):"
                )
            )
            for row in rows:
                self.stdout.write(f"    - {row}")
        if clean:
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK — {len(report)} schema(s) checked, no table drift."
                )
            )
