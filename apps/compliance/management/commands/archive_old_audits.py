"""
Management command to archive or delete old audit logs based on retention policy.

Usage:
    python manage.py archive_old_audits [--dry-run] [--days=DAYS]

Options:
    --dry-run: Show what would be deleted without making changes
    --days: Number of days to retain (default: 90)

Environment Variables:
    AUDIT_LOG_RETENTION_DAYS: Override default retention period
    ACCESS_LOG_RETENTION_DAYS: Separate retention for access logs
    ACTIVITY_SESSION_RETENTION_DAYS: Separate retention for user sessions
"""

import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.compliance.models_audit import AuditLog, AccessLog, UserActivitySession


class Command(BaseCommand):
    help = "Archive or delete old audit logs based on retention policy"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without making changes",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Number of days to retain (overrides env settings)",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        days_override = options.get("days")

        # Get retention periods from env or use defaults
        audit_log_days = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))
        access_log_days = int(os.getenv("ACCESS_LOG_RETENTION_DAYS", "30"))
        session_days = int(os.getenv("ACTIVITY_SESSION_RETENTION_DAYS", "60"))

        # Override if --days specified
        if days_override is not None:
            audit_log_days = access_log_days = session_days = days_override

        now = timezone.now()

        # Calculate cutoff dates
        audit_cutoff = now - timedelta(days=audit_log_days)
        access_cutoff = now - timedelta(days=access_log_days)
        session_cutoff = now - timedelta(days=session_days)

        # Find old records
        old_audits = AuditLog.objects.filter(timestamp__lt=audit_cutoff)
        old_access = AccessLog.objects.filter(timestamp__lt=access_cutoff)
        old_sessions = UserActivitySession.objects.filter(
            login_timestamp__lt=session_cutoff
        )

        audit_count = old_audits.count()
        access_count = old_access.count()
        session_count = old_sessions.count()

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] Would delete:"))
            self.stdout.write(
                f"  - {audit_count} AuditLog records (older than {audit_log_days} days)"
            )
            self.stdout.write(
                f"  - {access_count} AccessLog records (older than {access_log_days} days)"
            )
            self.stdout.write(
                f"  - {session_count} UserActivitySession records (older than {session_days} days)"
            )
            self.stdout.write("\nOldest records:")

            if audit_count > 0:
                oldest_audit = old_audits.order_by("timestamp").first()
                self.stdout.write(f"  AuditLog: {oldest_audit.timestamp}")

            if access_count > 0:
                oldest_access = old_access.order_by("timestamp").first()
                self.stdout.write(f"  AccessLog: {oldest_access.timestamp}")

            if session_count > 0:
                oldest_session = old_sessions.order_by("login_timestamp").first()
                self.stdout.write(
                    f"  UserActivitySession: {oldest_session.login_timestamp}"
                )
        else:
            # Delete old records
            audit_deleted, _ = old_audits.delete()
            access_deleted, _ = old_access.delete()
            session_deleted, _ = old_sessions.delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Deleted {audit_deleted} audit logs, {access_deleted} access logs, "
                    f"{session_deleted} activity sessions"
                )
            )

            if audit_deleted + access_deleted + session_deleted == 0:
                self.stdout.write(self.style.SUCCESS("No old records found to archive"))

            # Summary
            self.stdout.write("\nRetention policy:")
            self.stdout.write(f"  - AuditLog: {audit_log_days} days")
            self.stdout.write(f"  - AccessLog: {access_log_days} days")
            self.stdout.write(f"  - UserActivitySession: {session_days} days")
