from __future__ import annotations

"""
Read-only deep health check for a single tenant.

Usage examples:

    python manage.py tenant_health_check --slug gilead-school
    python manage.py tenant_health_check --domain gilead-school.runmycampus.com
    python manage.py tenant_health_check --schema gilead_school

This command does NOT mutate any data. It:
  - Resolves the tenant Client + School
  - Prints schema_name and known domains
  - Switches into the tenant schema and verifies that key tables exist
  - Prints row counts for a small set of important tenant tables
"""

from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Print schema and key table health for a single tenant (read-only)."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--slug",
            help="School.slug for the tenant (e.g. gilead-school).",
        )
        group.add_argument(
            "--domain",
            help="Full tenant domain (e.g. gilead-school.runmycampus.com).",
        )
        group.add_argument(
            "--schema",
            help="Client.schema_name (PostgreSQL schema, e.g. gilead_school).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if not getattr(settings, "USE_DJANGO_TENANTS", False):
            raise CommandError("USE_DJANGO_TENANTS is not enabled.")
        if connection.vendor != "postgresql":
            raise CommandError("tenant_health_check requires PostgreSQL (django-tenants).")

        from apps.customers.models import Client, Domain
        from apps.schools.models import School

        slug = (options.get("slug") or "").strip()
        domain = (options.get("domain") or "").strip().lower()
        schema_name = (options.get("schema") or "").strip().lower()

        client = None
        school = None

        if slug:
            school = School.objects.filter(slug=slug).first()
            if not school:
                raise CommandError(f"No School found with slug={slug!r}")
            client = Client.objects.filter(school=school).first()
            if not client:
                raise CommandError(f"No Client (tenant) found for School slug={slug!r}")
        elif domain:
            dom = Domain.objects.filter(domain=domain).select_related("tenant").first()
            if not dom or not dom.tenant:
                raise CommandError(f"No Domain/Client found for domain={domain!r}")
            client = dom.tenant
            school = getattr(client, "school", None)
        elif schema_name:
            client = Client.objects.filter(schema_name=schema_name).first()
            if not client:
                raise CommandError(f"No Client found with schema_name={schema_name!r}")
            school = getattr(client, "school", None)

        if not client:
            raise CommandError("Unable to resolve tenant Client from provided arguments.")

        # Basic identity summary
        self.stdout.write(self.style.SUCCESS("Tenant identity"))
        self.stdout.write(f"  Client id:       {client.id}")
        self.stdout.write(f"  Client name:     {client.name!r}")
        self.stdout.write(f"  schema_name:     {client.schema_name!r}")
        if school:
            self.stdout.write(f"  School id:       {school.id}")
            self.stdout.write(f"  School name:     {school.name!r}")
            self.stdout.write(f"  School slug:     {school.slug!r}")
        else:
            self.stdout.write("  School:          <none linked>")

        domains: Iterable[Domain] = Domain.objects.filter(tenant=client).order_by("domain")
        if domains:
            self.stdout.write("  Domains:")
            for d in domains:
                primary = " (primary)" if d.is_primary else ""
                self.stdout.write(f"    - {d.domain}{primary}")
        else:
            self.stdout.write("  Domains:         <none>")

        # Switch into tenant schema and perform read-only checks.
        try:
            from django_tenants.utils import tenant_context
        except ImportError as exc:
            raise CommandError(f"django-tenants is not installed correctly: {exc}") from exc

        key_tables = {
            # Core academic lifecycle
            "schools_school": "Schools (shared app, but visible in tenant context)",
            "academics_academicyear": "AcademicYear",
            "academics_term": "Term",
            "academics_classroom": "Classroom",
            # People
            "people_studentprofile": "StudentProfile",
            "people_staffprofile": "StaffProfile",
            # Finance
            "finance_complianceprofile": "Finance ComplianceProfile",
            "finance_invoice": "Invoice",
            "finance_payment": "Payment",
            # Reports
            "reports_reportcard": "ReportCard",
        }

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Schema health (read-only)"))
        with tenant_context(client):
            current_schema = getattr(connection, "schema_name", None)
            self.stdout.write(f"  Current connection.schema_name: {current_schema!r}")

            existing_tables = set(connection.introspection.table_names())

            with connection.cursor() as cursor:
                for table_name, label in key_tables.items():
                    if table_name not in existing_tables:
                        self.stdout.write(self.style.WARNING(f"  [MISSING] {table_name} ({label})"))
                        continue
                    count = self._safe_count_rows(cursor, table_name)
                    self.stdout.write(self.style.SUCCESS(f"  [OK] {table_name:<32} ({label})  rows={count}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done. No data was modified."))

    def _safe_count_rows(self, cursor, table_name: str) -> int:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        except Exception:
            # If counting fails (e.g. permissions, RLS), report -1 to indicate unknown.
            return -1

