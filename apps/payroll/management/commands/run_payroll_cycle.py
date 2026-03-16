from __future__ import annotations

from calendar import monthrange
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, IntegrityError
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.automation.models import AutomationExecutionLog
from apps.payroll.models import PayrollRun
from apps.payroll.services import (
    generate_payslips,
    get_active_payroll_profile,
)
from apps.platform_runtime.structured_logging import log_exception_with_context

# §2.4: Typed allowlist for run_payroll_cycle handle() (profile, get_or_create, generate_payslips, mark_completed).
_PAYROLL_RUN_CYCLE_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValidationError,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    return first, date(year, month, last_day)


class Command(BaseCommand):
    help = "Generate payroll run for a month (defaults to the current month)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            help="Year for the payroll run.",
        )
        parser.add_argument(
            "--month",
            type=int,
            choices=range(1, 13),
            help="Month (1-12) for the payroll run.",
        )

    def handle(self, *args, **options):
        execution_log = AutomationExecutionLog.objects.create(
            task_name="payroll.run_payroll_cycle",
            execution_type=AutomationExecutionLog.ExecutionType.MANUAL,
            status=AutomationExecutionLog.Status.PENDING,
        )

        profile = get_active_payroll_profile()
        if not profile:
            execution_log.mark_completed(
                AutomationExecutionLog.Status.FAILED,
                error_message="No active compliance profile configured for payroll.",
            )
            raise CommandError("No active compliance profile configured for payroll.")

        try:
            year = options.get("year")
            month = options.get("month")
            today = timezone.now().date()
            if year and month:
                start, end = _month_bounds(year, month)
            else:
                start = today.replace(day=1)
                last_day = monthrange(today.year, today.month)[1]
                end = date(today.year, today.month, last_day)

            run, created = PayrollRun.objects.get_or_create(
                profile=profile,
                period_start=start,
                period_end=end,
                defaults={
                    "created_at": timezone.now(),
                    "status": PayrollRun.Status.DRAFT,
                },
            )
            if not created:
                self.stdout.write("Payroll run already exists for that period; regenerating payslips.")

            payslips = generate_payslips(run)
            summary = {
                "payroll_run_id": run.id,
                "period_start": str(start),
                "period_end": str(end),
                "created_new_run": created,
                "payslips_generated": len(payslips),
            }
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                records_processed=len(payslips),
                summary=summary,
            )
            self.stdout.write(self.style.SUCCESS(f"Payroll run {run} processed with {len(payslips)} payslips."))
        except _PAYROLL_RUN_CYCLE_ERRORS as exc:
            school_id = getattr(profile, "school_id", None) if profile else None
            log_exception_with_context(
                "run_payroll_cycle: payroll run failed",
                school_id=school_id,
                extra={
                    "command": "run_payroll_cycle",
                    "period_start": period_start_str,
                    "period_end": period_end_str,
                    "error": str(exc),
                },
            )
            execution_log.mark_completed(
                AutomationExecutionLog.Status.FAILED,
                error_message=str(exc),
            )
            raise
