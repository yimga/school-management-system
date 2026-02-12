"""
Verify custom domains: resolve DNS and set custom_domain_verified (Phase 4 whitelabel).
Run: python manage.py verify_custom_domains
Uses socket.getaddrinfo to check that the custom_domain resolves; optional CNAME check.
"""
import socket
from django.core.management.base import BaseCommand
from apps.schools.models import School


class Command(BaseCommand):
    help = "Verify school custom domains via DNS and set custom_domain_verified."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only print, do not update.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        for school in School.objects.exclude(custom_domain="").filter(custom_domain__isnull=False):
            domain = (school.custom_domain or "").strip()
            if not domain:
                continue
            try:
                socket.getaddrinfo(domain, 443)
                if not school.custom_domain_verified:
                    if not dry_run:
                        school.custom_domain_verified = True
                        school.save(update_fields=["custom_domain_verified", "updated_at"])
                    self.stdout.write(self.style.SUCCESS(f"{school.name}: {domain} resolves -> verified"))
                else:
                    self.stdout.write(f"{school.name}: {domain} already verified")
            except (socket.gaierror, OSError) as e:
                if school.custom_domain_verified:
                    if not dry_run:
                        school.custom_domain_verified = False
                        school.save(update_fields=["custom_domain_verified", "updated_at"])
                    self.stdout.write(self.style.WARNING(f"{school.name}: {domain} no longer resolves -> unverified"))
                else:
                    self.stdout.write(self.style.NOTICE(f"{school.name}: {domain} does not resolve ({e})"))
