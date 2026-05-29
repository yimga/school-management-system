"""Organization-level multi-currency balance rollup (global governance Phase 3C).

Aggregates open AR invoice balances per school under an ``Organization`` without
FX conversion — each row stays in its native currency so operators see honest
multi-currency exposure.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.governance.models import Organization
    from apps.schools.models import School

_OPEN_INVOICE_STATUSES = ("ISSUED", "PARTIAL", "OVERDUE")


@dataclass(frozen=True)
class SchoolCurrencyBalance:
    school_id: str
    school_name: str
    currency_code: str
    open_balance: Decimal
    open_invoice_count: int


def _invoice_currency_code(invoice) -> str:
    currency_fk = getattr(invoice, "currency", None)
    if currency_fk is not None:
        code = getattr(currency_fk, "code", None) or getattr(currency_fk, "pk", None)
        if code:
            return str(code).upper()
    profile = getattr(invoice, "profile", None)
    if profile is not None:
        profile_code = getattr(profile, "currency_code", "") or ""
        if profile_code:
            return str(profile_code).upper()
    return ""


def consolidated_org_balances(organization: "Organization") -> list[SchoolCurrencyBalance]:
    """
    Sum open invoice balances for every school linked to ``organization``.

    Returns one ``SchoolCurrencyBalance`` per (school, currency) pair with
    positive exposure. No cross-currency conversion is applied.
    """
    from apps.finance.models import Invoice
    from apps.schools.models import School

    if organization is None or getattr(organization, "pk", None) is None:
        return []

    # tenant-isolation-allow: org-fx-rollup-explicit-organization-school-fk-scope
    schools = list(School.objects.filter(organization=organization).only("id", "name"))
    if not schools:
        return []

    school_by_id: dict[str, School] = {str(s.pk): s for s in schools}
    school_pks = [s.pk for s in schools]

    rows: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"open_balance": Decimal("0.00"), "open_invoice_count": 0}
    )

    invoices = (
        Invoice.objects.filter(
            school_id__in=school_pks,
            status__in=_OPEN_INVOICE_STATUSES,
        )
        .select_related("profile", "currency")
    )

    for invoice in invoices:
        school_id = str(invoice.school_id)
        if school_id not in school_by_id:
            continue
        currency_code = _invoice_currency_code(invoice)
        if not currency_code:
            continue
        balance = Decimal(getattr(invoice, "balance_amount", 0) or 0)
        if balance <= Decimal("0"):
            continue
        bucket = rows[(school_id, currency_code)]
        bucket["open_balance"] = bucket["open_balance"] + balance  # type: ignore[operator]
        bucket["open_invoice_count"] = int(bucket["open_invoice_count"]) + 1  # type: ignore[arg-type]

    out: list[SchoolCurrencyBalance] = []
    for (school_id, currency_code), agg in sorted(rows.items()):
        school = school_by_id[school_id]
        out.append(
            SchoolCurrencyBalance(
                school_id=school_id,
                school_name=school.name,
                currency_code=currency_code,
                open_balance=agg["open_balance"],  # type: ignore[arg-type]
                open_invoice_count=int(agg["open_invoice_count"]),  # type: ignore[arg-type]
            )
        )
    return out
