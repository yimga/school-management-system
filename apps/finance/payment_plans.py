"""
Payment plans and installments — platform integration point (Section 15.3).
Required; integrated with Invoice/Payment. Full PaymentPlan/RecurringPaymentSubscription
models re-introduction when DB tables are re-added (see advanced_payments.py and migration 0045).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone


def get_payment_plan_scope() -> dict[str, Any]:
    """
    Single integration point for payment-plan capability. Required by platform.
    Returns current scope: installments via Invoice/FeeInstallment; full PaymentPlan when re-introduced.
    """
    return {
        "installments_via_invoice": True,
        "installments_via_fee_installment": True,
        "payment_plan_model": False,
        "recurring_subscription_model": False,
        "message": "Installments via Invoice due dates and FeeInstallment; PaymentPlan/RecurringPaymentSubscription re-introduction when DB tables re-added (section_15_scope_implemented_and_roadmap.md 15.3).",
    }


def schedule_installment_due_dates(
    total_amount: Decimal,
    num_installments: int,
    first_due: date | None = None,
    frequency: str = "MONTHLY",
) -> list[tuple[date, Decimal]]:
    """
    Return a list of (due_date, amount) for installments. Equal split; integrates with Invoice/InvoiceLine.
    Used by fee/invoice flows that support payment plans. Required; no optional behaviour.
    """
    if num_installments <= 0:
        return []
    first_due = first_due or timezone.now().date()
    amount_per = (total_amount / num_installments).quantize(Decimal("0.01"))
    remainder = total_amount - (amount_per * num_installments)
    delta = timedelta(days=30) if frequency == "MONTHLY" else timedelta(days=7)
    due_dates = []
    cur = first_due
    for i in range(num_installments):
        amt = amount_per + (remainder if i == 0 else Decimal("0"))
        due_dates.append((cur, amt))
        cur = cur + delta
    return due_dates
