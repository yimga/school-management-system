"""
Phase I: Create django-tenants Client and Domain from existing School rows.

Run only when USE_DJANGO_TENANTS=1 and after migrate_schemas --shared.
For each School: create Client (schema_name=normalized slug, name, school=School)
and Domain(s) (subdomain + base_domain, and custom_domain if set).

Usage: python manage.py migrate_schools_to_tenants [--dry-run]
"""

import os
from django.core.management.base import BaseCommand
from django.db import IntegrityError, connection


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
        parser.add_argument(
            "--dry-run", action="store_true", help="Only print what would be created."
        )

    def handle(self, *args, **options):
        from django.conf import settings

        use_tenants = os.getenv("USE_DJANGO_TENANTS", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not use_tenants and not getattr(settings, "USE_DJANGO_TENANTS", False):
            self.stdout.write(
                self.style.WARNING(
                    "Schema-per-tenant is not enabled. Set USE_DJANGO_TENANTS=1 (or use PostgreSQL for default)."
                )
            )
            return
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.ERROR("django-tenants requires PostgreSQL."))
            return
        try:
            from apps.schools.models import School
            from apps.schools.host_routing import get_canonical_base_domain
            from apps.customers.models import Client, Domain
        except ImportError as e:
            self.stdout.write(
                self.style.ERROR(
                    "Import failed (enable USE_DJANGO_TENANTS and customers app): %s"
                    % e
                )
            )
            return
        dry_run = options.get("dry_run", False)
        base_domain = get_canonical_base_domain()

        def ensure_domains(client, school):
            """Idempotently attach the subdomain + verified custom domain.

            Re-runnable: only the FIRST domain for a brand-new tenant claims
            ``is_primary``; existing rows are left untouched by get_or_create.
            """
            primary = not Domain.objects.filter(tenant=client).exists()
            if school.subdomain:
                domain_str = "%s.%s" % (school.subdomain.strip().lower(), base_domain)
                _, made = Domain.objects.get_or_create(
                    domain=domain_str,
                    defaults={"tenant": client, "is_primary": primary},
                )
                if made:
                    primary = False
            if school.custom_domain and school.custom_domain_verified:
                Domain.objects.get_or_create(
                    domain=school.custom_domain.strip().lower(),
                    defaults={"tenant": client, "is_primary": primary},
                )

        created = 0
        healed = 0
        for school in School.objects.filter(is_active=True).order_by("name"):
            schema_name = _normalize_schema_name(school.slug)
            # Idempotency: a Client may already exist for this school. The unique
            # constraint is on school_id (customers_client_school_id_key), and the
            # stored schema_name can legitimately diverge from the current slug
            # (slug renamed after creation, or the tenant was created via the live
            # provisioning path). Guard on BOTH columns so a re-run never re-INSERTs
            # and trips the school_id unique constraint — which would crash the
            # whole pre-deploy (this command runs under `set -e`).
            existing = (
                Client.objects.filter(school=school).first()
                or Client.objects.filter(schema_name=schema_name).first()
            )
            if existing is not None:
                self.stdout.write(
                    "Skip (already exists): %s schema_name=%s"
                    % (school.name, existing.schema_name)
                )
                if not dry_run:
                    ensure_domains(existing, school)  # self-heal any missing Domain rows
                    healed += 1
                continue
            if dry_run:
                self.stdout.write(
                    "Would create Client name=%s schema_name=%s school=%s"
                    % (school.name, schema_name, school.id)
                )
                if school.subdomain:
                    self.stdout.write(
                        "  Domain: %s.%s" % (school.subdomain, base_domain)
                    )
                if school.custom_domain and school.custom_domain_verified:
                    self.stdout.write("  Domain: %s" % school.custom_domain)
                created += 1
                continue
            try:
                # NOT wrapped in transaction.atomic(): Client.auto_create_schema
                # is True, so save() runs CREATE SCHEMA + per-tenant migrations,
                # which django-tenants must not do inside an outer transaction.
                # The command runs in autocommit, so a failed INSERT (the first
                # op in save(), before any schema work) rolls back cleanly and
                # leaves the connection usable.
                client = Client(
                    schema_name=schema_name,
                    name=school.name,
                    school=school,
                )
                client.save()
                ensure_domains(client, school)
            except IntegrityError as exc:
                # A concurrent deploy step or the provisioning path won the race
                # and already created this tenant. Never abort the whole
                # pre-deploy for one school — log and move on.
                self.stdout.write(
                    self.style.WARNING(
                        "Skip (already created concurrently): %s (%s)"
                        % (school.name, exc.__class__.__name__)
                    )
                )
                continue
            created += 1
            self.stdout.write(
                "Created Client %s schema_name=%s" % (school.name, schema_name)
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Done. Created %s tenant(s); healed domains on %s existing."
                % (created, healed)
            )
        )
