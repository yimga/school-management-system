from __future__ import annotations

"""
Read-only deep health check for a single tenant.

Usage examples:

    python manage.py tenant_health_check --slug sample-school
    python manage.py tenant_health_check --domain sample-school.runmycampus.com
    python manage.py tenant_health_check --schema sample_school

This command does NOT mutate any data. It:
  - Resolves the tenant Client + School
  - Prints schema_name and known domains
  - Switches into the tenant schema and verifies that key tables exist
  - Prints row counts for a small set of important tenant tables
"""

from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.schools.repositories.health_repository import (
    check_table_exists,
    count_table_rows,
)


class Command(BaseCommand):
    help = "Print schema and key table health for a single tenant (read-only)."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--slug",
            help="School.slug for the tenant (e.g. sample-school).",
        )
        group.add_argument(
            "--domain",
            help="Full tenant domain (e.g. sample-school.runmycampus.com).",
        )
        group.add_argument(
            "--schema",
            help="Client.schema_name (PostgreSQL schema, e.g. sample_school).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if not getattr(settings, "USE_DJANGO_TENANTS", False):
            raise CommandError("USE_DJANGO_TENANTS is not enabled.")
        if connection.vendor != "postgresql":
            raise CommandError(
                "tenant_health_check requires PostgreSQL (django-tenants)."
            )

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
            raise CommandError(
                "Unable to resolve tenant Client from provided arguments."
            )

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

        domains: Iterable[Domain] = Domain.objects.filter(tenant=client).order_by(
            "domain"
        )
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
            raise CommandError(
                f"django-tenants is not installed correctly: {exc}"
            ) from exc

        # Shared tables live in the public schema even when you're in tenant_context.
        shared_tables = {
            ("public", "schools_school"): "School (shared)",
            ("public", "siteconfig_sitesettings"): "SiteSettings (shared)",
        }

        # Tenant tables live in the tenant schema.
        tenant_tables = {
            # Core academic lifecycle
            ("academics", "academicyear"): "AcademicYear",
            ("academics", "term"): "Term",
            ("academics", "classroom"): "Classroom",
            # People
            ("people", "studentprofile"): "StudentProfile",
            ("people", "teacherprofile"): "TeacherProfile",
            ("people", "employerprofile"): "EmployerProfile",
            # Finance
            ("finance", "complianceprofile"): "Finance ComplianceProfile",
            ("finance", "invoice"): "Invoice",
            ("finance", "payment"): "Payment",
            # Reports
            ("reports", "reportcard"): "ReportCard",
        }

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Schema health (read-only)"))
        with tenant_context(client):
            current_schema = getattr(connection, "schema_name", None)
            self.stdout.write(f"  Current connection.schema_name: {current_schema!r}")

            # Shared schema checks (explicitly public)
            for schema, table in shared_tables:
                full = f"{schema}.{table}"
                exists = check_table_exists(full)
                if not exists:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [MISSING] {full} ({shared_tables[(schema, table)]})"
                        )
                    )
                    continue
                count = count_table_rows(schema, table)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [OK] {full:<36} ({shared_tables[(schema, table)]})  rows={count}"
                    )
                )

            # Tenant schema checks (explicitly the tenant schema)
            tenant_schema = client.schema_name
            for app_label, model_table in tenant_tables:
                table = f"{app_label}_{model_table}"
                full = f"{tenant_schema}.{table}"
                exists = check_table_exists(full)
                if not exists:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [MISSING] {full} ({tenant_tables[(app_label, model_table)]})"
                        )
                    )
                    continue
                count = count_table_rows(tenant_schema, table)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [OK] {full:<36} ({tenant_tables[(app_label, model_table)]})  rows={count}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done. No data was modified."))
