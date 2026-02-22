"""
Phase I: Create django-tenants Client and Domain from existing School rows.

Run only when USE_DJANGO_TENANTS=1 and after migrate_schemas --shared.
For each School: create Client (schema_name=normalized slug, name, school=School)
and Domain(s) (subdomain + base_domain, and custom_domain if set).

Usage: python manage.py migrate_schools_to_tenants [--dry-run]
"""
import os
from django.core.management.base import BaseCommand
from django.db import connection


def _normalize_schema_name(slug: str, max_length: int = 63) -> str:
    """PostgreSQL schema name: lowercase, replace - with _."""
    s = (slug or "").strip().lower().replace("-", "_")
    for c in s:
        if c != "_" and not c.isalnum():
            s = s.replace(c, "_")
    return s[:max_length] or "tenant"


class Command(BaseCommand):
    help = "Create Client and Domain for each School (Phase I schema-per-tenant migration)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only print what would be created.")

    def handle(self, *args, **options):
        if not os.getenv("USE_DJANGO_TENANTS", "").strip() in ("1", "true", "yes"):
            self.stdout.write(self.style.WARNING("Set USE_DJANGO_TENANTS=1 to use this command."))
            return
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.ERROR("django-tenants requires PostgreSQL."))
            return
        try:
            from apps.schools.models import School
            from apps.customers.models import Client, Domain
        except ImportError as e:
            self.stdout.write(self.style.ERROR("Import failed (enable USE_DJANGO_TENANTS and customers app): %s" % e))
            return
        dry_run = options.get("dry_run", False)
        base_domain = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip() or "localhost"
        created = 0
        for school in School.objects.filter(is_active=True).order_by("name"):
            schema_name = _normalize_schema_name(school.slug)
            if Client.objects.filter(schema_name=schema_name).exists():
                self.stdout.write("Skip (already exists): %s schema_name=%s" % (school.name, schema_name))
                continue
            if dry_run:
                self.stdout.write("Would create Client name=%s schema_name=%s school=%s" % (school.name, schema_name, school.id))
                if school.subdomain:
                    self.stdout.write("  Domain: %s.%s" % (school.subdomain, base_domain))
                if school.custom_domain and school.custom_domain_verified:
                    self.stdout.write("  Domain: %s" % school.custom_domain)
                created += 1
                continue
            client = Client(
                schema_name=schema_name,
                name=school.name,
                school=school,
            )
            client.save()
            primary = True
            if school.subdomain:
                domain_str = "%s.%s" % (school.subdomain.strip().lower(), base_domain)
                Domain.objects.get_or_create(domain=domain_str, defaults={"tenant": client, "is_primary": primary})
                primary = False
            if school.custom_domain and school.custom_domain_verified:
                Domain.objects.get_or_create(
                    domain=school.custom_domain.strip().lower(),
                    defaults={"tenant": client, "is_primary": primary},
                )
            created += 1
            self.stdout.write("Created Client %s schema_name=%s" % (school.name, schema_name))
        self.stdout.write(self.style.SUCCESS("Done. Created %s tenant(s)." % created))