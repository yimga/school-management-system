"""Create signed compliance archives and optionally purge their exact rows."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.utils import timezone

from apps.compliance.audit_retention import (
    archive_and_optionally_purge,
    retention_queryset,
)
from apps.compliance.models_audit import AuditLog, AccessLog, UserActivitySession


class Command(BaseCommand):
    help = "Archive old compliance records; purge only with explicit approval"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Show eligible and held counts"
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retention days for every target (overrides DATA_RETENTION)",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Purge exact archived rows after checksum/signature verification",
        )
        parser.add_argument(
            "--approval-token",
            default="",
            help="Must match AUDIT_RETENTION_APPROVAL_TOKEN when --purge is used",
        )

    def handle(self, *args, **options):
        if options["purge"] and options["dry_run"]:
            raise CommandError("--purge and --dry-run cannot be combined.")

        retention = getattr(settings, "DATA_RETENTION", {})
        override = options["days"]
        targets = [
            (AuditLog, "timestamp", override or retention.get("audit_log_days", 365)),
            (AccessLog, "timestamp", override or retention.get("access_log_days", 180)),
            (
                UserActivitySession,
                "login_timestamp",
                override or retention.get("session_days", 90),
            ),
        ]
        now = timezone.now()
        for model, timestamp_field, days in targets:
            days = int(days)
            if days <= 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"{model.__name__}: skipped because retention is disabled"
                    )
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
            if not result.archive:
                self.stdout.write(
                    f"{model.__name__}: no eligible records; "
                    f"{result.held_count} protected by legal hold"
                )
                continue
            operation = "archived and purged" if options["purge"] else "archived"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{model.__name__}: {operation} {result.eligible_count} records "
                    f"as {result.archive.archive_id}; "
                    f"{result.held_count} protected by legal hold"
                )
            )
