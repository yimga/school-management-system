"""
Management command to send batched alert digests.

Usage:
    python manage.py send_digest_alerts [--frequency=FREQ] [--dry-run]

Options:
    --frequency: 'hourly' or 'daily' (default: hourly)
    --dry-run: Show what would be sent without sending
"""

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.compliance.models_audit import AlertDigest
from apps.platform_runtime.structured_logging import log_exception_with_context

# §2.4: Typed tuple for digest email send (allowlist 0).
import smtplib

_SEND_DIGEST_ALERTS_EMAIL_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    AttributeError,
    TypeError,
    ValueError,
    smtplib.SMTPException,
)


class Command(BaseCommand):
    help = "Send batched alert digests (hourly/daily)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--frequency",
            type=str,
            default="hourly",
            choices=["hourly", "daily"],
            help="Digest frequency (hourly or daily)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be sent without sending",
        )

    def handle(self, *args, **options):
        frequency = options.get("frequency", "hourly")
        dry_run = options.get("dry_run", False)

        # Determine time window
        now = timezone.now()
        if frequency == "hourly":
            cutoff = now - timedelta(hours=1)
            window_desc = "last hour"
        else:  # daily
            cutoff = now - timedelta(days=1)
            window_desc = "last 24 hours"

        # Get pending alerts in window
        pending = AlertDigest.objects.filter(
            is_sent=False, created_at__gte=cutoff
        ).order_by("created_at")

        count = pending.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(f"✅ No pending alerts in {window_desc}")
            )
            return

        # Group alerts by type and severity
        by_type = defaultdict(lambda: {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0})
        alert_list = []

        for alert in pending:
            by_type[alert.alert_type][alert.severity] += 1
            alert_list.append(
                {
                    "type": alert.alert_type,
                    "severity": alert.severity,
                    "subject": alert.subject,
                    "message": alert.message,
                    "created_at": alert.created_at,
                }
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would send digest with {count} alerts from {window_desc}"
                )
            )
            self.stdout.write("\nBreakdown by type and severity:")
            for alert_type, counts in by_type.items():
                total = sum(counts.values())
                self.stdout.write(f"  {alert_type}: {total} total")
                for severity, count in counts.items():
                    if count > 0:
                        self.stdout.write(f"    - {severity}: {count}")

            self.stdout.write("\nFirst 5 alerts:")
            for alert in alert_list[:5]:
                self.stdout.write(
                    f"  [{alert['severity']}] {alert['subject']} ({alert['created_at'].strftime('%Y-%m-%d %H:%M')})"
                )
        else:
            # Send the digest
            self._send_digest(frequency, by_type, alert_list, window_desc)

            # Mark alerts as sent
            pending.update(is_sent=True, sent_at=now)

            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Sent digest with {count} alerts from {window_desc}"
                )
            )

    def _send_digest(self, frequency, by_type, alert_list, window_desc):
        """Send the actual digest email/notification."""
        from apps.compliance.alerts import send_email_alert

        # Build digest subject
        total_count = len(alert_list)
        subject = (
            f"[{frequency.title()} Digest] {total_count} Security/Compliance Alerts"
        )

        # Build digest body
        message_lines = [
            f"Alert Digest for {window_desc}",
            f"Total Alerts: {total_count}",
            "",
            "Breakdown by Type:",
        ]

        for alert_type, counts in by_type.items():
            total = sum(counts.values())
            message_lines.append(f"  {alert_type}: {total}")
            for severity, count in counts.items():
                if count > 0:
                    message_lines.append(f"    - {severity}: {count}")

        message_lines.extend(["", "Detailed Alerts:", ""])

        for alert in alert_list:
            message_lines.append(
                f"[{alert['severity']}] {alert['type']}: {alert['subject']}"
            )
            message_lines.append(
                f"  Time: {alert['created_at'].strftime('%Y-%m-%d %H:%M:%S')}"
            )
            message_lines.append(f"  {alert['message']}")
            message_lines.append("")

        message = "\n".join(message_lines)

        # Send via email (assuming send_email_alert exists in alerts.py)
        try:
            send_email_alert(subject, message)
            self.stdout.write(self.style.SUCCESS(f"📧 Digest email sent"))
        except _SEND_DIGEST_ALERTS_EMAIL_ERRORS as e:
            log_exception_with_context(
                "send_digest_alerts: failed to send digest email",
                school_id=None,
                extra={
                    "command": "send_digest_alerts",
                    "frequency": frequency,
                    "error": str(e),
                },
            )
            self.stdout.write(self.style.ERROR(f"❌ Failed to send digest: {e}"))
