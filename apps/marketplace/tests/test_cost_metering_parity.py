"""Tests for marketplace ↔ finance cost-metering parity.

12-pillar audit P5 follow-up. The marketplace ledger
(``AppBillingLedger``) records what a tenant *should* be charged for
their installed apps; the finance side (``Invoice`` / receipts)
records what is *actually* invoiced. If the two diverge, tenant
billing is wrong — either over- or under-charging. This module asserts
the parity invariant.

Parity rule (per-school, per-currency, by month):

    SUM(AppBillingLedger.amount for kind in {install_fee, subscription, usage, proration_debit})
    - SUM(AppBillingLedger.amount for kind = proration_credit)
    == SUM(Invoice.amount for ledger-sourced invoices in the same window)

Tolerance: ``Decimal("0.01")`` per school+currency+month bucket to
absorb rounding when multiple ledger lines collapse into one invoice
line (the finance side typically aggregates at issue time).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.test import SimpleTestCase


def cost_metering_delta(
    ledger_entries: Iterable[dict],
    invoice_amounts: Iterable[dict],
    *,
    tolerance: Decimal = Decimal("0.01"),
) -> list[dict]:
    """Pure helper: compare ledger sums to invoice sums per bucket.

    Both inputs are iterables of dicts with at least
    ``{"school_id", "currency", "month", "amount", ...}``. Ledger
    entries additionally carry ``"kind"`` so we can apply the
    debit/credit polarity rule.

    Returns a list of out-of-tolerance buckets. Empty list = parity OK.
    """
    debits = {"install_fee", "subscription", "usage", "proration_debit"}
    credits = {"proration_credit"}
    by_bucket: dict[tuple, Decimal] = {}
    for entry in ledger_entries:
        key = (entry["school_id"], entry["currency"], entry["month"])
        amt = Decimal(str(entry.get("amount", 0)))
        kind = entry.get("kind", "")
        if kind in debits:
            by_bucket[key] = by_bucket.get(key, Decimal(0)) + amt
        elif kind in credits:
            by_bucket[key] = by_bucket.get(key, Decimal(0)) - amt
    for inv in invoice_amounts:
        key = (inv["school_id"], inv["currency"], inv["month"])
        amt = Decimal(str(inv.get("amount", 0)))
        by_bucket[key] = by_bucket.get(key, Decimal(0)) - amt
    return [
        {"school_id": k[0], "currency": k[1], "month": k[2], "delta": delta}
        for k, delta in by_bucket.items()
        if abs(delta) > tolerance
    ]


class CostMeteringHelperTests(SimpleTestCase):
    def test_zero_ledger_zero_invoice_is_parity(self):
        self.assertEqual(cost_metering_delta([], []), [])

    def test_install_fee_with_matching_invoice(self):
        ledger = [{"school_id": 1, "currency": "USD", "month": "2026-05", "kind": "install_fee", "amount": "100.00"}]
        invoices = [{"school_id": 1, "currency": "USD", "month": "2026-05", "amount": "100.00"}]
        self.assertEqual(cost_metering_delta(ledger, invoices), [])

    def test_missing_invoice_flagged(self):
        ledger = [{"school_id": 1, "currency": "USD", "month": "2026-05", "kind": "subscription", "amount": "50.00"}]
        delta = cost_metering_delta(ledger, [])
        self.assertEqual(len(delta), 1)
        self.assertEqual(delta[0]["delta"], Decimal("50.00"))

    def test_proration_credit_subtracts_from_ledger(self):
        # 100 subscription - 30 credit = 70 net; invoice should be 70.
        ledger = [
            {"school_id": 1, "currency": "USD", "month": "2026-05", "kind": "subscription", "amount": "100.00"},
            {"school_id": 1, "currency": "USD", "month": "2026-05", "kind": "proration_credit", "amount": "30.00"},
        ]
        invoices = [{"school_id": 1, "currency": "USD", "month": "2026-05", "amount": "70.00"}]
        self.assertEqual(cost_metering_delta(ledger, invoices), [])

    def test_tolerance_absorbs_rounding(self):
        # 99.99 ledger vs 100.00 invoice -- within 0.01 tolerance.
        ledger = [{"school_id": 1, "currency": "USD", "month": "2026-05", "kind": "subscription", "amount": "99.99"}]
        invoices = [{"school_id": 1, "currency": "USD", "month": "2026-05", "amount": "100.00"}]
        self.assertEqual(cost_metering_delta(ledger, invoices), [])

    def test_overcharge_above_tolerance_flagged(self):
        # 100 ledger vs 105 invoice -> overcharge by 5 (flagged as -5).
        ledger = [{"school_id": 1, "currency": "USD", "month": "2026-05", "kind": "subscription", "amount": "100.00"}]
        invoices = [{"school_id": 1, "currency": "USD", "month": "2026-05", "amount": "105.00"}]
        delta = cost_metering_delta(ledger, invoices)
        self.assertEqual(len(delta), 1)
        self.assertEqual(delta[0]["delta"], Decimal("-5.00"))

    def test_per_school_isolation(self):
        # Two schools with offsetting balances must NOT cancel each other.
        ledger = [
            {"school_id": 1, "currency": "USD", "month": "2026-05", "kind": "subscription", "amount": "100.00"},
        ]
        invoices = [
            {"school_id": 2, "currency": "USD", "month": "2026-05", "amount": "100.00"},
        ]
        delta = cost_metering_delta(ledger, invoices)
        self.assertEqual(len(delta), 2)  # both buckets out of parity

    def test_per_currency_isolation(self):
        # USD vs EUR must be separate buckets even for same school.
        ledger = [
            {"school_id": 1, "currency": "USD", "month": "2026-05", "kind": "subscription", "amount": "100.00"},
        ]
        invoices = [
            {"school_id": 1, "currency": "EUR", "month": "2026-05", "amount": "100.00"},
        ]
        delta = cost_metering_delta(ledger, invoices)
        self.assertEqual(len(delta), 2)
