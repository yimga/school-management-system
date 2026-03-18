"""
Purge old compliance data based on retention policy.
Usage:
    manage.py purge_compliance_data [--dry-run] [--region=GDPR]

Retention windows are controlled by DATA_RETENTION settings. Use default keys
(audit_log_days, access_log_days, session_days, report_days) or region-specific
keys when --region is set (e.g. GDPR_audit_log_days). Respects compliance_region
by using per-region retention when provided.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.compliance.models_audit import (
    AuditLog,
    AccessLog,
    UserActivitySession,
    ComplianceReport,
)


class Command(BaseCommand):
    help = "Purge compliance data according to retention policy"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Show counts only, do not delete"
        )
        parser.add_argument(
            "--region",
            type=str,
            default="",
            help="Compliance region (e.g. GDPR, FERPA, NDPR). Uses region-prefixed keys in DATA_RETENTION when set.",
        )

    def handle(self, *args, **options):
        retention = getattr(settings, "DATA_RETENTION", {})
        now = timezone.now()
        region = (options.get("region") or "").strip().upper()
        prefix = f"{region}_" if region else ""

        targets = [
            (AuditLog, "timestamp", "audit_log_days"),
            (AccessLog, "timestamp", "access_log_days"),
            (UserActivitySession, "login_timestamp", "session_days"),
            (ComplianceReport, "generated_at", "report_days"),
        ]

        for model, field_name, key in targets:
            days = int(retention.get(prefix + key, retention.get(key, 0)))
            if days <= 0:
                self.stdout.write(
                    self.style.WARNING(f"Skipping {model.__name__}: retention disabled")
                )
                continue

            cutoff = now - timedelta(days=days)
            qs = model.objects.filter(**{f"{field_name}__lt": cutoff})

            count = qs.count()
            if options["dry_run"]:
                self.stdout.write(
                    f"{model.__name__}: would delete {count} records older than {days} days"
                )
            else:
                deleted, _ = qs.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{model.__name__}: deleted {deleted} records older than {days} days"
                    )
                )

        self.stdout.write(self.style.SUCCESS("Purge complete"))
