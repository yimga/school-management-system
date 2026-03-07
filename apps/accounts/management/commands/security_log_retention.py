"""
Security log retention (plan 3.15): delete logs older than 1 year (GDPR/Bill 64).
Optional: anonymize IP after 90 days (keep country only).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import SecurityAuditLog


class Command(BaseCommand):
    help = "Delete SecurityAuditLog older than 1 year; optionally anonymize IP after 90 days."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report counts, do not delete.")
        parser.add_argument("--anonymize-days", type=int, default=90, help="Anonymize IP for logs older than N days (0=disable).")
        parser.add_argument("--delete-days", type=int, default=365, help="Delete logs older than N days.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        anonymize_days = options["anonymize_days"]
        delete_days = options["delete_days"]
        now = timezone.now()
        cutoff_delete = now - timedelta(days=delete_days)
        cutoff_anonymize = now - timedelta(days=anonymize_days) if anonymize_days else None

        to_delete = SecurityAuditLog.objects.filter(created_at__lt=cutoff_delete)
        count_delete = to_delete.count()
        if count_delete:
            self.stdout.write(f"Would delete {count_delete} logs older than {delete_days} days (before {cutoff_delete.date()}).")
            if not dry_run:
                to_delete.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted {count_delete} logs."))
        else:
            self.stdout.write("No logs to delete.")

        if cutoff_anonymize and anonymize_days > 0:
            to_anon = SecurityAuditLog.objects.filter(created_at__lt=cutoff_anonymize).exclude(ip_address="").exclude(ip_address__isnull=True)
            count_anon = to_anon.count()
            if count_anon:
                self.stdout.write(f"Would anonymize IP for {count_anon} logs older than {anonymize_days} days.")
                if not dry_run:
                    for log in to_anon.only("id", "ip_address"):
                        if log.ip_address and "..." not in (log.ip_address or ""):
                            parts = (log.ip_address or "").split(".")
                            if len(parts) >= 2:
                                log.ip_address = f"{parts[0]}.{parts[1]}.0.0"
                            else:
                                log.ip_address = (log.ip_address or "")[:10] + "..."
                            log.save(update_fields=["ip_address"])
                    self.stdout.write(self.style.SUCCESS(f"Anonymized {count_anon} logs."))
        return
