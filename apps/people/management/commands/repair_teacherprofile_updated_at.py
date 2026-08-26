"""
Heal drifted people_* columns on public + every tenant schema.

django-tenants applies TENANT_APPS only via migrate_schemas --tenant. Legacy
people_* tables left in the public schema never receive those migrations, which
breaks manager.runmycampus.com views that resolve teacher_profile on the public
connection (500: column does not exist). The same drift family covers
``client_offline_id`` (migration 0057/0059), and merge tombstones
``merged_into_id`` / guardian ``is_active`` (migration 0064/0068) — so this
command runs the full ``ensure_people_schema_current`` repair bundle.

Run automatically from render_predeploy.sh after migrate_schemas.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from apps.people.schema_repair import ensure_people_schema_current


class Command(BaseCommand):
    help = (
        "Heal drifted people_* columns (updated_at, offline-sync incl. "
        "client_offline_id, merge tombstones incl. merged_into_id) when the "
        "table exists but a column is missing (public legacy + tenant schemas)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            action="append",
            dest="schemas",
            metavar="NAME",
            help="Limit to specific PostgreSQL schema(s). Default: public + all tenants.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write("repair_teacherprofile_updated_at: skip (not PostgreSQL)")
            return

        schema_names = options.get("schemas") or []
        if not schema_names:
            schema_names = ["public"]
            if getattr(settings, "USE_DJANGO_TENANTS", False):
                from django_tenants.utils import get_tenant_model

                Tenant = get_tenant_model()
                for client in Tenant.objects.exclude(schema_name="public").only(
                    "schema_name"
                ):
                    name = (getattr(client, "schema_name", None) or "").strip()
                    if name and name not in schema_names:
                        schema_names.append(name)

        repaired = 0
        for schema_name in schema_names:
            try:
                from django_tenants.utils import schema_context
            except ImportError:
                schema_context = None  # type: ignore[assignment,misc]

            ctx = (
                schema_context(schema_name)
                if schema_context is not None
                else _nullcontext()
            )
            with ctx:
                if ensure_people_schema_current():
                    repaired += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  {schema_name}: healed people_* columns "
                            "(updated_at / offline-sync / merge tombstones)"
                        )
                    )
                else:
                    self.stdout.write(
                        f"  {schema_name}: ok (columns present or tables absent)"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"repair_teacherprofile_updated_at: complete ({repaired} schema(s) repaired)"
            )
        )


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False
