"""Wave R-C (v3.96.0 — 2026-05-26) — Family billing aggregator.

A parent / guardian who has three children at the school today has to open
three different student-fee views to see the family's total balance. This
module is the one-call aggregator the parent dashboard renders against.

Inputs:
- ``guardian_user_id`` — the parent / guardian.
- A ``children_runner`` callback (default uses the live ``StudentGuardian``
  bridge); the seam keeps the algorithm unit-testable without spinning up
  the ORM.
- A ``balance_runner`` callback (default sums the live ``Invoice`` rows per
  child).

Outputs:
- ``FamilyBillingSummary`` — total due / paid / overdue, per-child rollups
  with currency, status enum.
- ``propose_payment_split(...)`` — FIFO algorithm allocating a single
  payment across the family's overdue then due invoices. Caller decides
  whether to actually apply.

Tenant isolation: the children-runner already constrains by ``school`` FK
(StudentGuardian rows live under StudentProfile.school). The balance-runner
fetches Invoices with ``student_id__in=<children>`` — same tenant guarantee
by transitivity, audited via ``# tenant-isolation-allow`` markers.

ZERO new migrations. Pure-Python kernel composing over existing
``Invoice`` / ``StudentGuardian`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from decimal import Decimal
from typing import Callable


# --- Status enum (mirrors apps.finance.models.Invoice.Status) -------------

DRAFT = "DRAFT"
ISSUED = "ISSUED"
PARTIAL = "PARTIAL"
PAID = "PAID"
OVERDUE = "OVERDUE"
VOID = "VOID"

_OPEN_STATUSES = (ISSUED, PARTIAL, OVERDUE)
_TERMINAL_STATUSES = (PAID, VOID, DRAFT)


# --- Data shapes -----------------------------------------------------------


@dataclass(frozen=True)
class InvoiceLite:
    """A normalized invoice row from the balance runner."""

    invoice_id: int
    student_id: int
    total_amount: Decimal
    balance_amount: Decimal
    currency: str
    status: str
    due_date: date_type | None = None
    reference: str = ""


@dataclass(frozen=True)
class StudentLite:
    student_id: int
    display_name: str
    grade_level: str = ""


@dataclass
class ChildBillingRow:
    student: StudentLite
    total_due: Decimal = Decimal("0")
    total_balance_open: Decimal = Decimal("0")
    overdue_balance: Decimal = Decimal("0")
    open_invoice_count: int = 0
    overdue_invoice_count: int = 0
    currency: str = ""

    def as_dict(self) -> dict:
        return {
            "student_id": self.student.student_id,
            "display_name": self.student.display_name,
            "grade_level": self.student.grade_level,
            "total_due": str(self.total_due),
            "total_balance_open": str(self.total_balance_open),
            "overdue_balance": str(self.overdue_balance),
            "open_invoice_count": self.open_invoice_count,
            "overdue_invoice_count": self.overdue_invoice_count,
            "currency": self.currency,
        }


@dataclass
class FamilyBillingSummary:
    guardian_user_id: int
    child_rows: list[ChildBillingRow] = field(default_factory=list)
    family_total_open_balance: Decimal = Decimal("0")
    family_overdue_balance: Decimal = Decimal("0")
    currency_mismatch: bool = False
    canonical_currency: str = ""

    @property
    def has_open_balance(self) -> bool:
        return self.family_total_open_balance > Decimal("0")

    @property
    def has_overdue(self) -> bool:
        return self.family_overdue_balance > Decimal("0")

    def as_dict(self) -> dict:
        return {
            "guardian_user_id": self.guardian_user_id,
            "child_rows": [r.as_dict() for r in self.child_rows],
            "family_total_open_balance": str(self.family_total_open_balance),
            "family_overdue_balance": str(self.family_overdue_balance),
            "currency_mismatch": self.currency_mismatch,
            "canonical_currency": self.canonical_currency,
            "has_open_balance": self.has_open_balance,
            "has_overdue": self.has_overdue,
        }


@dataclass
class PaymentSplitLine:
    invoice_id: int
    student_id: int
    allocated_amount: Decimal
    currency: str


@dataclass
class PaymentSplitProposal:
    total_proposed: Decimal
    leftover: Decimal
    lines: list[PaymentSplitLine] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total_proposed": str(self.total_proposed),
            "leftover": str(self.leftover),
            "lines": [
                {
                    "invoice_id": l.invoice_id,
                    "student_id": l.student_id,
                    "allocated_amount": str(l.allocated_amount),
                    "currency": l.currency,
                }
                for l in self.lines
            ],
            "blocked_reasons": list(self.blocked_reasons),
        }


# --- Runners (the DB seam) -------------------------------------------------


ChildrenRunner = Callable[[int], list[StudentLite]]
BalanceRunner = Callable[[list[int]], list[InvoiceLite]]


def _default_children_runner(guardian_user_id: int) -> list[StudentLite]:
    from apps.people.models import StudentGuardian  # type: ignore

    # tenant-isolation-allow: family-billing-children-via-guardian-bridge-school-scoped-by-student-fk
    links = (
        StudentGuardian.objects
        .filter(guardian_user_id=guardian_user_id)
        .select_related("student")
    )
    out: list[StudentLite] = []
    for link in links:
        s = link.student
        if s is None:
            continue
        display = f"{s.first_name} {s.last_name}".strip() or f"Student #{s.id}"
        out.append(
            StudentLite(
                student_id=s.id,
                display_name=display,
                grade_level=getattr(s, "grade_level", "") or "",
            )
        )
    return out


def _default_balance_runner(student_ids: list[int]) -> list[InvoiceLite]:
    if not student_ids:
        return []
    from apps.finance.models import Invoice  # type: ignore

    # tenant-isolation-allow: family-billing-invoices-confined-to-children-of-guardian-same-school
    rows = (
        Invoice.objects
        .filter(student_id__in=student_ids)
        .exclude(status=VOID)
        .select_related("profile")
    )
    out: list[InvoiceLite] = []
    for inv in rows:
        currency = ""
        prof = getattr(inv, "profile", None)
        if prof is not None:
            currency = getattr(prof, "currency_code", "") or ""
        out.append(
            InvoiceLite(
                invoice_id=inv.id,
                student_id=inv.student_id,
                total_amount=Decimal(inv.total_amount or 0),
                balance_amount=Decimal(getattr(inv, "balance_amount", 0) or 0),
                currency=currency,
                status=inv.status,
                due_date=getattr(inv, "due_date", None),
                reference=getattr(inv, "reference", "") or "",
            )
        )
    return out


# --- The aggregator -------------------------------------------------------


def aggregate_family_balance(
    *,
    guardian_user_id: int,
    today: date_type | None = None,
    children_runner: ChildrenRunner | None = None,
    balance_runner: BalanceRunner | None = None,
) -> FamilyBillingSummary:
    cr = children_runner or _default_children_runner
    br = balance_runner or _default_balance_runner

    children = cr(guardian_user_id)
    summary = FamilyBillingSummary(guardian_user_id=guardian_user_id)
    if not children:
        return summary

    child_lookup: dict[int, ChildBillingRow] = {
        c.student_id: ChildBillingRow(student=c) for c in children
    }
    invoices = br([c.student_id for c in children])

    currencies: set[str] = set()
    for inv in invoices:
        row = child_lookup.get(inv.student_id)
        if row is None:
            continue
        if not row.currency and inv.currency:
            row.currency = inv.currency
        if inv.currency:
            currencies.add(inv.currency)
        if inv.status in _OPEN_STATUSES:
            row.total_due += inv.total_amount
            row.total_balance_open += inv.balance_amount
            row.open_invoice_count += 1
            is_overdue = inv.status == OVERDUE or (
                inv.due_date is not None
                and today is not None
                and inv.due_date < today
                and inv.balance_amount > Decimal("0")
            )
            if is_overdue:
                row.overdue_balance += inv.balance_amount
                row.overdue_invoice_count += 1

    summary.child_rows = list(child_lookup.values())
    summary.family_total_open_balance = sum(
        (r.total_balance_open for r in summary.child_rows), Decimal("0"),
    )
    summary.family_overdue_balance = sum(
        (r.overdue_balance for r in summary.child_rows), Decimal("0"),
    )
    if len(currencies) > 1:
        summary.currency_mismatch = True
    if currencies:
        # Pick the most-common currency as canonical for display headers.
        # Stable: alphabetical when tied.
        counts: dict[str, int] = {}
        for inv in invoices:
            if inv.currency:
                counts[inv.currency] = counts.get(inv.currency, 0) + 1
        summary.canonical_currency = sorted(
            counts.items(), key=lambda kv: (-kv[1], kv[0]),
        )[0][0]
    return summary


# --- Payment split (FIFO across overdue → due) ----------------------------


def propose_payment_split(
    *,
    guardian_user_id: int,
    payment_amount: Decimal,
    today: date_type | None = None,
    children_runner: ChildrenRunner | None = None,
    balance_runner: BalanceRunner | None = None,
) -> PaymentSplitProposal:
    """Allocate ``payment_amount`` across the family's open invoices.

    Order: oldest-due-date first; within same date, smallest balance first
    (clears small fees first so the parent sees more invoices marked done).
    Currency mismatch blocks the split (the caller must pick a currency).
    """
    if payment_amount <= Decimal("0"):
        return PaymentSplitProposal(
            total_proposed=Decimal("0"),
            leftover=Decimal("0"),
            blocked_reasons=["payment_amount_must_be_positive"],
        )

    cr = children_runner or _default_children_runner
    br = balance_runner or _default_balance_runner
    children = cr(guardian_user_id)
    if not children:
        return PaymentSplitProposal(
            total_proposed=Decimal("0"),
            leftover=payment_amount,
            blocked_reasons=["no_children_linked_to_guardian"],
        )

    invoices = [
        inv for inv in br([c.student_id for c in children])
        if inv.status in _OPEN_STATUSES and inv.balance_amount > Decimal("0")
    ]
    if not invoices:
        return PaymentSplitProposal(
            total_proposed=Decimal("0"),
            leftover=payment_amount,
            blocked_reasons=["no_open_invoices"],
        )
    currencies = {inv.currency for inv in invoices if inv.currency}
    if len(currencies) > 1:
        return PaymentSplitProposal(
            total_proposed=Decimal("0"),
            leftover=payment_amount,
            blocked_reasons=["currency_mismatch:" + ",".join(sorted(currencies))],
        )

    invoices.sort(key=lambda i: (
        i.due_date or date_type.max,
        i.balance_amount,
    ))

    remaining = payment_amount
    proposal = PaymentSplitProposal(total_proposed=Decimal("0"), leftover=Decimal("0"))
    for inv in invoices:
        if remaining <= Decimal("0"):
            break
        allocated = min(remaining, inv.balance_amount)
        proposal.lines.append(
            PaymentSplitLine(
                invoice_id=inv.invoice_id,
                student_id=inv.student_id,
                allocated_amount=allocated,
                currency=inv.currency,
            )
        )
        remaining -= allocated
    proposal.total_proposed = payment_amount - remaining
    proposal.leftover = remaining
    return proposal
