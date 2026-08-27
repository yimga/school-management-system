"""
Tenant scheduled report emails: process ``TenantReportSchedule`` rows where next_run <= now.
Usage: python manage.py send_scheduled_reports [--dry-run] [--school-id ID] [--limit N]
    [--strict-no-skip] [--json-summary]
"""

import json
import logging
from smtplib import SMTPException

from django.core.management.base import BaseCommand, CommandError
from django.core.mail import EmailMessage
from django.db import DatabaseError, IntegrityError
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.reports.models import TenantReportSchedule
from apps.reports.schedule_utils import compute_next_scheduled_run

logger = logging.getLogger(__name__)

_SCHEDULED_REPORT_RUN_ONE_ERRORS = (
    DatabaseError,
    IntegrityError,
    OSError,
    ConnectionError,
    TimeoutError,
    SMTPException,
    TypeError,
    ValueError,
)


class Command(BaseCommand):
    help = "Run tenant scheduled reports (TenantReportSchedule) and email recipients."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List due schedules without sending.",
        )
        parser.add_argument(
            "--school-id",
            type=int,
            default=None,
            help="Only process schedules for this school primary key.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most this many due schedules (after ordering by next_run).",
        )
        parser.add_argument(
            "--strict-no-skip",
            action="store_true",
            help="Exit with error if any due schedule had no recipient addresses.",
        )
        parser.add_argument(
            "--json-summary",
            action="store_true",
            help="Emit a final JSON line with run statistics (operators / CI).",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        school_id = options.get("school_id")
        limit = options.get("limit")
        json_summary = bool(options.get("json_summary"))
        strict_no_skip = bool(options.get("strict_no_skip"))
        if limit is not None and limit < 1:
            raise CommandError("--limit must be a positive integer.")
        now = timezone.now()
        qs = TenantReportSchedule.objects.filter(
            is_active=True,
            next_run__lte=now,
        ).select_related("school", "created_by")
        if school_id is not None:
            qs = qs.filter(school_id=school_id)
        due = list(qs.order_by("next_run", "id"))
        if limit is not None:
            due = due[:limit]
        if not due:
            if school_id is not None:
                self.stdout.write(
                    f"No due schedules for school_id={school_id} (check next_run and is_active)."
                )
            else:
                self.stdout.write("No scheduled reports due.")
            if json_summary:
                self._write_json_summary(
                    {
                        "processed": 0,
                        "emailed": 0,
                        "skipped_no_recipients": 0,
                        "failed": 0,
                    },
                    dry_run=dry_run,
                    school_id=school_id,
                )
            return
        self.stdout.write(f"Found {len(due)} due schedule(s).")
        stats = {
            "processed": 0,
            "emailed": 0,
            "skipped_no_recipients": 0,
            "failed": 0,
        }
        for sr in due:
            if dry_run:
                stats["processed"] += 1
                if not (isinstance(sr.recipients, list) and sr.recipients):
                    stats["skipped_no_recipients"] += 1
                warn = ""
                if not (isinstance(sr.recipients, list) and sr.recipients):
                    warn = " [WARNING: no recipient addresses]"
                self.stdout.write(
                    f"  Would run: [{sr.school.slug}] {sr.name} -> {sr.recipients}{warn}"
                )
                continue
            try:
                emailed, skipped = self._run_one(sr, now)
                stats["processed"] += 1
                if emailed:
                    stats["emailed"] += 1
                if skipped:
                    stats["skipped_no_recipients"] += 1
            except _SCHEDULED_REPORT_RUN_ONE_ERRORS as e:
                stats["failed"] += 1
                log_exception_with_context(
                    "send_scheduled_reports: run_one failed",
                    school_id=getattr(sr, "school_id", None),
                    extra={
                        "command": "send_scheduled_reports",
                        "scheduled_report_id": getattr(sr, "id", None),
                    },
                    exc_info=True,
                )
                self.stderr.write(self.style.ERROR(f"Failed {sr}: {e}"))
        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    f"Dry-run summary: {stats['processed']} schedule(s); "
                    f"{stats['skipped_no_recipients']} lack recipient address(es)."
                )
            )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    "Done: "
                    f"processed={stats['processed']} "
                    f"emailed={stats['emailed']} "
                    f"skipped_no_recipients={stats['skipped_no_recipients']} "
                    f"failed={stats['failed']}"
                )
            )
        if json_summary:
            self._write_json_summary(stats, dry_run=dry_run, school_id=school_id)
        if strict_no_skip and stats["skipped_no_recipients"] > 0:
            raise CommandError(
                f"--strict-no-skip: {stats['skipped_no_recipients']} due schedule(s) "
                "had no recipient addresses."
            )
        if stats["failed"] > 0:
            raise CommandError(
                f"send_scheduled_reports: {stats['failed']} schedule run(s) failed."
            )

    def _write_json_summary(
        self, stats: dict, *, dry_run: bool, school_id: int | None
    ) -> None:
        payload = {
            "command": "send_scheduled_reports",
            "dry_run": dry_run,
            "school_id": school_id,
            **stats,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))

    def _run_one(self, sr: TenantReportSchedule, now) -> tuple[bool, bool]:
        """
        Returns (emailed, skipped_no_recipients).
        ``skipped_no_recipients`` is True when no email was sent because the list is empty.
        """
        has_addresses = isinstance(sr.recipients, list) and bool(sr.recipients)
        if not has_addresses:
            logger.warning(
                "send_scheduled_reports skipped_no_recipients school_id=%s schedule_id=%s name=%r",
                sr.school_id,
                sr.pk,
                sr.name,
            )
            self.stderr.write(
                self.style.WARNING(
                    f"Active schedule id={sr.pk} ({sr.name!r}) has no recipient addresses; email skipped."
                )
            )
        body = (
            f"Scheduled report: {sr.name}\n"
            f"Report key: {sr.report_key}\n"
            f"School: {sr.school.name}\n"
            f"Parameters: {sr.parameters}"
        )
        subject = f"Scheduled report: {sr.name}"
        emailed = False
        if has_addresses:
            msg = EmailMessage(
                subject=subject,
                body=body,
                to=sr.recipients,
            )
            msg.send(fail_silently=False)
            emailed = True
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent {sr.name} (school={sr.school.slug}) to {sr.recipients}"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Processed {sr.name} (school={sr.school.slug}) — no email (empty recipients)"
                )
            )
        sr.last_run = now
        sr.next_run = compute_next_scheduled_run(
            sr.last_run,
            sr.schedule_frequency,
            sr.schedule_time,
            school=sr.school,
        )
        sr.save()
        return emailed, not has_addresses
