"""
Backfill SchoolDomain from School.subdomain and School.custom_domain.
Run after 0021_add_schooldomain is applied. Safe to run multiple times (idempotent).
"""
import os
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backfill SchoolDomain from School.subdomain and School.custom_domain (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only print what would be created.")
        parser.add_argument("--base-domain", type=str, default=None, help="Override base domain (default: MULTI_TENANT_BASE_DOMAIN or runyourcampus.com).")

    def handle(self, *args, **options):
        from apps.schools.models import School, SchoolDomain
        from apps.schools.domain_sync import sync_school_domains_to_runtime

        base_domain = (options.get("base_domain") or os.getenv("MULTI_TENANT_BASE_DOMAIN") or "runyourcampus.com").strip().lower()
        dry_run = options.get("dry_run", False)
        created = 0
        for school in School.objects.filter(is_active=True):
            if school.subdomain:
                domain_str = f"{school.subdomain}.{base_domain}".lower()
                if not SchoolDomain.objects.filter(school=school, domain=domain_str).exists():
                    if dry_run:
                        self.stdout.write("Would create SchoolDomain: %s -> %s (SUBDOMAIN)" % (domain_str, school.name))
                    else:
                        SchoolDomain.objects.create(
                            school=school,
                            domain=domain_str,
                            kind="SUBDOMAIN",
                            is_verified=True,
                        )
                    created += 1
            if school.custom_domain and school.custom_domain_verified:
                domain_str = school.custom_domain.strip().lower()
                if not SchoolDomain.objects.filter(school=school, domain=domain_str).exists():
                    if dry_run:
                        self.stdout.write("Would create SchoolDomain: %s -> %s (CUSTOM)" % (domain_str, school.name))
                    else:
                        SchoolDomain.objects.create(
                            school=school,
                            domain=domain_str,
                            kind="CUSTOM",
                            is_verified=True,
                        )
                    created += 1
            if not dry_run:
                sync_school_domains_to_runtime(school)
        self.stdout.write(self.style.SUCCESS("Done. Created %s SchoolDomain(s)." % created))
