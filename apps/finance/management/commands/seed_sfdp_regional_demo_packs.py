"""Seed 12 synthetic regional demo schools (SFDP 1472)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.finance.regional_payment_profiles import list_supported_country_codes
from apps.schools.models import School

DEMO_PACKS: tuple[tuple[str, str, str], ...] = (
    ("sfdp-demo-ng", "SFDP Demo Nigeria", "NG"),
    ("sfdp-demo-gh", "SFDP Demo Ghana", "GH"),
    ("sfdp-demo-cm", "SFDP Demo Cameroon", "CM"),
    ("sfdp-demo-ke", "SFDP Demo Kenya", "KE"),
    ("sfdp-demo-br", "SFDP Demo Brazil", "BR"),
    ("sfdp-demo-in", "SFDP Demo India", "IN"),
    ("sfdp-demo-id", "SFDP Demo Indonesia", "ID"),
    ("sfdp-demo-ae", "SFDP Demo UAE", "AE"),
    ("sfdp-demo-fr", "SFDP Demo France", "FR"),
    ("sfdp-demo-ca", "SFDP Demo Canada", "CA"),
    ("sfdp-demo-mx", "SFDP Demo Mexico", "MX"),
    ("sfdp-demo-za", "SFDP Demo South Africa", "ZA"),
)


class Command(BaseCommand):
    help = "Create or update 12 SFDP regional demo schools with country codes in settings."

    def handle(self, *args, **options):
        supported = set(list_supported_country_codes())
        created = 0
        for slug, name, iso2 in DEMO_PACKS:
            if iso2 not in supported:
                self.stderr.write(f"Skip {slug}: {iso2} not in profile catalog")
                continue
            school, was_created = School.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "subdomain": slug.replace("_", "-")[:50],
                    "is_active": True,
                    "country_code": iso2,
                    "settings": {"sfdp_demo_pack": True, "demo_country": iso2},
                },
            )
            if was_created:
                created += 1
            self.stdout.write(f"{'Created' if was_created else 'Updated'} {school.slug} ({iso2})")
        self.stdout.write(self.style.SUCCESS(f"SFDP demo packs: {created} created, {len(DEMO_PACKS)} total"))
