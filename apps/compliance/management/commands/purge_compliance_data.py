"""Apply compliance retention using signed archive-before-purge bundles."""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.compliance.audit_retention import (
    archive_and_optionally_purge,
    retention_queryset,
)
from apps.compliance.models_audit import (
    AccessLog,
    AuditLog,
    ComplianceReport,
    UserActivitySession,
)


class Command(BaseCommand):
    help = "Archive compliance data and optionally purge with explicit approval"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Show counts only"
        )
        parser.add_argument(
            "--region",
            default="",
            help="Use region-prefixed DATA_RETENTION keys (for example GDPR)",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Purge exact rows only after their archive verifies",
        )
        parser.add_argument("--approval-token", default="")

    def handle(self, *args, **options):
        if options["purge"] and options["dry_run"]:
            raise CommandError("--purge and --dry-run cannot be combined.")
        retention = getattr(settings, "DATA_RETENTION", {})
        region = options["region"].strip().upper()
        prefix = f"{region}_" if region else ""
        targets = [
            (AuditLog, "timestamp", "audit_log_days"),
            (AccessLog, "timestamp", "access_log_days"),
            (UserActivitySession, "login_timestamp", "session_days"),
            (ComplianceReport, "generated_at", "report_days"),
        ]
        now = timezone.now()
        for model, timestamp_field, key in targets:
            days = int(retention.get(prefix + key, retention.get(key, 0)))
            if days <= 0:
                self.stdout.write(
                    self.style.WARNING(f"{model.__name__}: retention disabled")
                )
                continue
            cutoff = now - timedelta(days=days)
            eligible, held_count = retention_queryset(
                model, timestamp_field, cutoff
            )
            if options["dry_run"]:
                self.stdout.write(
                    f"{model.__name__}: would archive {eligible.count()} records; "
                    f"{held_count} protected by legal hold"
                )
                continue
            try:
                result = archive_and_optionally_purge(
                    model,
                    timestamp_field,
                    cutoff,
                    purge=options["purge"],
                    approval_token=options["approval_token"],
                )
            except (ImproperlyConfigured, PermissionDenied, OSError) as exc:
                raise CommandError(str(exc)) from exc
            if result.archive:
                operation = "archived and purged" if options["purge"] else "archived"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{model.__name__}: {operation} {result.eligible_count} "
                        f"records as {result.archive.archive_id}"
                    )
                )
            else:
                self.stdout.write(f"{model.__name__}: no eligible records")
            if result.held_count:
                self.stdout.write(
                    self.style.WARNING(
                        f"{model.__name__}: {result.held_count} records retained by legal hold"
                    )
                )
        self.stdout.write(self.style.SUCCESS("Compliance retention complete"))
