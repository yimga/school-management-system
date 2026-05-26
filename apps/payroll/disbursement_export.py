"""
Payroll disbursement export (global send — batch 1511).

Produces a CSV bank file for approved/processed payroll runs. Live mobile-money
salary APIs remain Lane 2; this closes repo-scope global send for bank transfer.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from django.utils import timezone

from apps.payroll.models import PayrollRun, Payslip


def build_disbursement_csv(run: PayrollRun) -> str:
    """ISO-20022-style flat CSV for operator upload to local banks."""
    payslips = (
        Payslip.objects.filter(payroll_run=run)
        .select_related("employee", "employee__user")
        .order_by("employee__user__last_name", "employee__user__first_name")
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "employee_code",
            "beneficiary_name",
            "payment_method",
            "bank_account",
            "mobile_money_number",
            "net_pay",
            "currency",
            "reference",
            "period_start",
            "period_end",
        ]
    )
    currency = getattr(run.profile, "currency_code", "USD") or "USD"
    ref_base = f"PAY-{run.pk}-{run.period_end.isoformat()}"
    for slip in payslips:
        emp = slip.employee
        user = emp.user
        name = (user.get_full_name() or user.username or "").strip()
        writer.writerow(
            [
                emp.employee_code or str(emp.pk),
                name,
                emp.get_payment_method_display()
                if hasattr(emp, "get_payment_method_display")
                else emp.payment_method,
                emp.bank_account or "",
                emp.mobile_money_number or "",
                str(slip.net_pay or Decimal("0.00")),
                currency,
                f"{ref_base}-{slip.pk}",
                run.period_start.isoformat(),
                run.period_end.isoformat(),
            ]
        )
    return buf.getvalue()


def disbursement_filename(run: PayrollRun) -> str:
    stamp = timezone.now().strftime("%Y%m%d")
    return f"payroll_disbursement_run{run.pk}_{stamp}.csv"
