"""
Phase 9: BI scheduled report emails.
Processes ScheduledReport (bi_models) where next_run <= now: run report, email recipients, set last_run/next_run.
Usage: python manage.py send_scheduled_reports [--dry-run]
"""

from datetime import timedelta
from smtplib import SMTPException

from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.db import DatabaseError, IntegrityError
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.reports.bi_models import ScheduledReport, ReportExecution

# Typed exceptions for §2.4 broad-except replacement (BACKLOG §2e row 6)
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


def _compute_next_run(last_run, frequency, schedule_time):
    """Compute next_run from last_run + frequency and schedule_time."""
    if last_run is None:
        base = timezone.now()
    else:
        base = last_run
    # Normalize to date and apply schedule_time
    base_date = base.date()
    next_naive = timezone.datetime.combine(
        base_date, schedule_time, tzinfo=timezone.get_current_timezone()
    )
    if next_naive <= base:
        next_naive = next_naive + timedelta(days=1)
    if frequency == "DAILY":
        next_run = next_naive
    elif frequency == "WEEKLY":
        next_run = next_naive + timedelta(days=7)
    elif frequency == "MONTHLY":
        if next_naive.month == 12:
            next_run = next_naive.replace(year=next_naive.year + 1, month=1)
        else:
            next_run = next_naive.replace(month=next_naive.month + 1)
    elif frequency == "QUARTERLY":
        next_run = next_naive + timedelta(days=90)
    else:
        next_run = next_naive + timedelta(days=1)
    return next_run


class Command(BaseCommand):
    help = "Run scheduled reports and email recipients (Phase 9: BI scheduled report emails)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List due schedules without sending.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        now = timezone.now()
        due = list(
            ScheduledReport.objects.filter(
                is_active=True,
                next_run__lte=now,
            ).select_related("report_definition", "created_by")
        )
        if not due:
            self.stdout.write("No scheduled reports due.")
            return
        self.stdout.write(f"Found {len(due)} due schedule(s).")
        for sr in due:
            if dry_run:
                self.stdout.write(
                    f"  Would run: {sr.report_definition.name} -> {sr.recipients}"
                )
                continue
            try:
                self._run_one(sr, now)
            except _SCHEDULED_REPORT_RUN_ONE_ERRORS as e:
                log_exception_with_context(
                    "send_scheduled_reports: run_one failed",
                    extra={
                        "command": "send_scheduled_reports",
                        "scheduled_report_id": getattr(sr, "id", None),
                        "report_definition_id": getattr(
                            getattr(sr, "report_definition", None), "id", None
                        ),
                    },
                    exc_info=True,
                )
                self.stderr.write(self.style.ERROR(f"Failed {sr}: {e}"))

    def _run_one(self, sr, now):
        rd = sr.report_definition
        execution = ReportExecution.objects.create(
            report_definition=rd,
            executed_by=sr.created_by,
            parameters=sr.parameters,
            status="RUNNING",
            started_at=now,
        )
        try:
            # Export: stub — in full implementation run query_template and attach CSV/PDF
            body = f"Scheduled report: {rd.name}\nReport type: {rd.report_type}\nParameters: {sr.parameters}"
            subject = f"Scheduled report: {rd.name}"
            if sr.recipients:
                msg = EmailMessage(
                    subject=subject,
                    body=body,
                    to=sr.recipients,
                )
                msg.send(fail_silently=False)
            execution.status = "COMPLETED"
            execution.completed_at = timezone.now()
        except _SCHEDULED_REPORT_RUN_ONE_ERRORS as e:
            execution.status = "FAILED"
            execution.error_message = str(e)
            execution.completed_at = timezone.now()
            rd = getattr(sr, "report_definition", None)
            log_exception_with_context(
                "send_scheduled_reports: run_one report send failed",
                school_id=getattr(rd, "school_id", None) if rd else None,
                extra={
                    "command": "send_scheduled_reports",
                    "scheduled_report_id": getattr(sr, "id", None),
                    "execution_id": getattr(execution, "id", None),
                    "report_definition_id": getattr(rd, "id", None) if rd else None,
                },
            )
            raise
        finally:
            execution.save()
        sr.last_run = now
        sr.next_run = _compute_next_run(
            sr.last_run, sr.schedule_frequency, sr.schedule_time
        )
        sr.save(update_fields=["last_run", "next_run"])
        self.stdout.write(self.style.SUCCESS(f"Sent {rd.name} to {sr.recipients}"))
