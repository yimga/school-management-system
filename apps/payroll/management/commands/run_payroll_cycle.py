from __future__ import annotations

from calendar import monthrange
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.payroll.models import PayrollRun
from apps.payroll.services import (
    generate_payslips,
    get_active_payroll_profile,
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
        profile = get_active_payroll_profile()
        if not profile:
            raise CommandError("No active compliance profile configured for payroll.")

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
        self.stdout.write(self.style.SUCCESS(f"Payroll run {run} processed with {len(payslips)} payslips."))
