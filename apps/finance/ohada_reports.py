from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from .models import Invoice, JournalLine, Payment, SuspensePayment


@dataclass
class DsfReportContext:
    start_date: date | None
    end_date: date | None
    balance_sheet: dict
    income_statement: dict
    cash_flow: dict
    annexes: dict


def _account_class(code: str) -> str:
    code = (code or "").strip()
    return code[:1] if code else ""


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation, ArithmeticError):
        return Decimal("0.00")


def build_dsf_report(profile, start_date: date | None = None, end_date: date | None = None) -> DsfReportContext:
    line_filter = Q(entry__profile=profile, entry__posted_at__isnull=False)
    if start_date:
        line_filter &= Q(entry__entry_date__gte=start_date)
    if end_date:
        line_filter &= Q(entry__entry_date__lte=end_date)

    line_rows = (
        JournalLine.objects.filter(line_filter)
        .values("account__code", "account__name", "account__account_type")
        .annotate(
            debit_total=Coalesce(Sum("debit"), Decimal("0.00")),
            credit_total=Coalesce(Sum("credit"), Decimal("0.00")),
        )
        .order_by("account__code")
    )

    class_totals = {str(i): Decimal("0.00") for i in range(1, 8)}
    asset_total = Decimal("0.00")
    liability_total = Decimal("0.00")
    equity_total = Decimal("0.00")
    revenue_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    cash_net_movement = Decimal("0.00")

    for row in line_rows:
        debit_total = _to_decimal(row.get("debit_total"))
        credit_total = _to_decimal(row.get("credit_total"))
        account_type = row.get("account__account_type")
        account_code = row.get("account__code") or ""

        cls = _account_class(account_code)
        if cls in class_totals:
            class_totals[cls] += debit_total - credit_total

        if account_type == "ASSET":
            net = debit_total - credit_total
            asset_total += net
            if cls == "5":
                cash_net_movement += net
        elif account_type == "LIABILITY":
            liability_total += credit_total - debit_total
        elif account_type == "EQUITY":
            equity_total += credit_total - debit_total
        elif account_type == "INCOME":
            revenue_total += credit_total - debit_total
        elif account_type == "EXPENSE":
            expense_total += debit_total - credit_total

    net_result = revenue_total - expense_total

    payments_qs = Payment.objects.filter(invoice__profile=profile, status="completed")
    invoices_qs = Invoice.objects.filter(profile=profile)
    if start_date:
        payments_qs = payments_qs.filter(paid_at__date__gte=start_date)
        invoices_qs = invoices_qs.filter(issued_date__gte=start_date)
    if end_date:
        payments_qs = payments_qs.filter(paid_at__date__lte=end_date)
        invoices_qs = invoices_qs.filter(issued_date__lte=end_date)

    cash_in = _to_decimal(payments_qs.aggregate(total=Sum("amount")).get("total"))
    cash_out = _to_decimal(
        payments_qs.filter(invoice__invoice_type=Invoice.InvoiceType.AP).aggregate(total=Sum("amount")).get("total")
    )
    closing_cash = cash_net_movement

    paid_receipt_count = payments_qs.exclude(receipt_number="").count()
    unresolved_suspense_qs = SuspensePayment.objects.filter(
        status__in=[SuspensePayment.Status.OPEN, SuspensePayment.Status.PARTIAL]
    )
    if start_date:
        unresolved_suspense_qs = unresolved_suspense_qs.filter(created_at__date__gte=start_date)
    if end_date:
        unresolved_suspense_qs = unresolved_suspense_qs.filter(created_at__date__lte=end_date)

    outstanding_ar = _to_decimal(
        invoices_qs.filter(
            invoice_type=Invoice.InvoiceType.AR,
            status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIAL, Invoice.Status.OVERDUE],
        ).aggregate(total=Sum("balance_amount")).get("total")
    )

    balance_sheet = {
        "assets_total": asset_total,
        "liabilities_total": liability_total,
        "equity_total": equity_total,
        "classes": class_totals,
    }
    income_statement = {
        "revenue_total": revenue_total,
        "expense_total": expense_total,
        "net_result": net_result,
    }
    cash_flow = {
        "cash_in": cash_in,
        "cash_out": cash_out,
        "net_cash_movement": cash_in - cash_out,
        "ledger_cash_movement": cash_net_movement,
        "closing_cash": closing_cash,
    }
    annexes = {
        "invoice_count": invoices_qs.count(),
        "payment_count": payments_qs.count(),
        "outstanding_ar": outstanding_ar,
        "estimated_stamp_duty_xaf": Decimal("1000.00") * Decimal(str(paid_receipt_count)),
        "unresolved_suspense_count": unresolved_suspense_qs.count(),
        "unresolved_suspense_amount": _to_decimal(
            unresolved_suspense_qs.aggregate(total=Sum("amount")).get("total")
        ),
        "payment_methods": list(
            payments_qs.values("method").annotate(total=Sum("amount")).order_by("method")
        ),
    }

    return DsfReportContext(
        start_date=start_date,
        end_date=end_date,
        balance_sheet=balance_sheet,
        income_statement=income_statement,
        cash_flow=cash_flow,
        annexes=annexes,
    )

