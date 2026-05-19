"""Seed payment.RegionalPaymentRailCatalog from finance.payment_region_catalog defaults."""

from django.core.management.base import BaseCommand

from apps.finance.payment_region_catalog import CANONICAL_PAYMENT_ORCHESTRATION_ISO2, _RAIL_DEFAULTS
from payment.models import RegionalPaymentRailCatalog


class Command(BaseCommand):
    help = "Seed RegionalPaymentRailCatalog rows from canonical finance rail defaults (G-22)."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for iso2 in sorted(CANONICAL_PAYMENT_ORCHESTRATION_ISO2):
            rails = _RAIL_DEFAULTS.get(iso2.upper())
            if not rails:
                continue
            primary = rails.get("primary") or {}
            backup = rails.get("backup") or {}
            obj, was_created = RegionalPaymentRailCatalog.objects.update_or_create(
                country_code=iso2.upper(),
                defaults={
                    "primary_rail_code": primary.get("code", ""),
                    "primary_rail_label": primary.get("label", ""),
                    "backup_rail_code": backup.get("code", ""),
                    "backup_rail_label": backup.get("label", ""),
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"RegionalPaymentRailCatalog: {created} created, {updated} updated."
            )
        )
