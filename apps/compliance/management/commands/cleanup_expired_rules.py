"""
Management command to deactivate expired IP/Country access rules.

Usage:
    python manage.py cleanup_expired_rules [--dry-run]

Options:
    --dry-run: Show what would be cleaned without making changes
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.compliance.models_audit import IPAccessRule


class Command(BaseCommand):
    help = "Deactivate expired IP and Country access rules"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be cleaned without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        now = timezone.now()

        # Find expired IP rules (CountryAccessRule doesn't have expires_at field)
        expired_ip_rules = IPAccessRule.objects.filter(
            expires_at__lte=now,
            is_active=True,
        )
        ip_count = expired_ip_rules.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would deactivate {ip_count} expired IP rules"
                )
            )
            if ip_count > 0:
                self.stdout.write("Expired IP Rules:")
                for rule in expired_ip_rules[:10]:  # Show first 10
                    self.stdout.write(f"  - {rule.ip_address} (expired {rule.expires_at})")
            else:
                self.stdout.write("No expired IP rules found")
        else:
            # Deactivate expired rules
            ip_updated = expired_ip_rules.update(is_active=False)

            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Deactivated {ip_updated} expired IP rules"
                )
            )

            if ip_updated == 0:
                self.stdout.write(self.style.SUCCESS("No expired rules found"))
