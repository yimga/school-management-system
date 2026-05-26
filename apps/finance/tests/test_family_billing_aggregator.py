"""Wave R-C (v3.96.0 — 2026-05-26) — Family billing aggregator tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.family_billing_aggregator import (
    ISSUED,
    OVERDUE,
    PAID,
    PARTIAL,
    InvoiceLite,
    StudentLite,
    aggregate_family_balance,
    propose_payment_split,
)


def _children(*ids_and_names) -> list[StudentLite]:
    out = []
    for sid, name in ids_and_names:
        out.append(StudentLite(student_id=sid, display_name=name, grade_level=""))
    return out


def _invoice(
    invoice_id, student_id, balance, *, status=ISSUED,
    total=None, currency="USD", due_date=None,
):
    if total is None:
        total = balance
    return InvoiceLite(
        invoice_id=invoice_id, student_id=student_id,
        total_amount=Decimal(str(total)), balance_amount=Decimal(str(balance)),
        currency=currency, status=status, due_date=due_date,
    )


class AggregateBasicTests(SimpleTestCase):

    def test_no_children_returns_zeroes(self):
        s = aggregate_family_balance(
            guardian_user_id=1,
            children_runner=lambda uid: [],
            balance_runner=lambda ids: [],
        )
        self.assertEqual(s.family_total_open_balance, Decimal("0"))
        self.assertEqual(s.child_rows, [])

    def test_single_child_open_balance(self):
        children = _children((10, "Ada Lovelace"))
        invs = [_invoice(1, 10, 500, status=ISSUED)]
        s = aggregate_family_balance(
            guardian_user_id=1,
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertEqual(len(s.child_rows), 1)
        self.assertEqual(s.family_total_open_balance, Decimal("500"))
        self.assertEqual(s.canonical_currency, "USD")
        self.assertFalse(s.currency_mismatch)
        self.assertTrue(s.has_open_balance)

    def test_paid_invoice_excluded_from_open(self):
        children = _children((10, "Ada"))
        invs = [
            _invoice(1, 10, 0, total=500, status=PAID),
            _invoice(2, 10, 200, status=ISSUED),
        ]
        s = aggregate_family_balance(
            guardian_user_id=1,
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertEqual(s.family_total_open_balance, Decimal("200"))

    def test_multi_child_rollup(self):
        children = _children((10, "Ada"), (11, "Babbage"))
        invs = [
            _invoice(1, 10, 500, status=ISSUED),
            _invoice(2, 11, 300, status=PARTIAL, total=600),
        ]
        s = aggregate_family_balance(
            guardian_user_id=1,
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertEqual(s.family_total_open_balance, Decimal("800"))
        ada_row = next(r for r in s.child_rows if r.student.student_id == 10)
        babb_row = next(r for r in s.child_rows if r.student.student_id == 11)
        self.assertEqual(ada_row.total_balance_open, Decimal("500"))
        self.assertEqual(babb_row.total_balance_open, Decimal("300"))


class OverdueTests(SimpleTestCase):

    def test_overdue_status_counts_even_without_today(self):
        children = _children((10, "Ada"))
        invs = [_invoice(1, 10, 100, status=OVERDUE)]
        s = aggregate_family_balance(
            guardian_user_id=1,
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertEqual(s.family_overdue_balance, Decimal("100"))
        self.assertTrue(s.has_overdue)

    def test_past_due_date_counts_when_today_supplied(self):
        children = _children((10, "Ada"))
        invs = [_invoice(
            1, 10, 100, status=ISSUED, due_date=date(2026, 1, 1),
        )]
        s = aggregate_family_balance(
            guardian_user_id=1,
            today=date(2026, 5, 26),
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertEqual(s.family_overdue_balance, Decimal("100"))

    def test_future_due_date_does_not_count_as_overdue(self):
        children = _children((10, "Ada"))
        invs = [_invoice(
            1, 10, 100, status=ISSUED, due_date=date(2027, 1, 1),
        )]
        s = aggregate_family_balance(
            guardian_user_id=1,
            today=date(2026, 5, 26),
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertEqual(s.family_overdue_balance, Decimal("0"))


class CurrencyMismatchTests(SimpleTestCase):

    def test_two_currencies_flagged(self):
        children = _children((10, "Ada"), (11, "Babbage"))
        invs = [
            _invoice(1, 10, 100, currency="USD"),
            _invoice(2, 11, 50000, currency="NGN"),
        ]
        s = aggregate_family_balance(
            guardian_user_id=1,
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertTrue(s.currency_mismatch)

    def test_canonical_is_most_frequent(self):
        children = _children((10, "Ada"), (11, "Babbage"))
        invs = [
            _invoice(1, 10, 100, currency="USD"),
            _invoice(2, 11, 200, currency="USD"),
            _invoice(3, 11, 50000, currency="NGN"),
        ]
        s = aggregate_family_balance(
            guardian_user_id=1,
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertEqual(s.canonical_currency, "USD")


class PaymentSplitTests(SimpleTestCase):

    def test_payment_must_be_positive(self):
        p = propose_payment_split(
            guardian_user_id=1,
            payment_amount=Decimal("0"),
            children_runner=lambda uid: [],
            balance_runner=lambda ids: [],
        )
        self.assertIn("payment_amount_must_be_positive", p.blocked_reasons)

    def test_no_children_returns_blocked(self):
        p = propose_payment_split(
            guardian_user_id=1,
            payment_amount=Decimal("100"),
            children_runner=lambda uid: [],
            balance_runner=lambda ids: [],
        )
        self.assertEqual(p.leftover, Decimal("100"))
        self.assertIn("no_children_linked_to_guardian", p.blocked_reasons)

    def test_no_open_invoices_returns_full_leftover(self):
        children = _children((10, "Ada"))
        p = propose_payment_split(
            guardian_user_id=1,
            payment_amount=Decimal("100"),
            children_runner=lambda uid: children,
            balance_runner=lambda ids: [_invoice(1, 10, 0, total=200, status=PAID)],
        )
        self.assertIn("no_open_invoices", p.blocked_reasons)

    def test_currency_mismatch_blocks(self):
        children = _children((10, "Ada"), (11, "Bab"))
        invs = [
            _invoice(1, 10, 100, currency="USD"),
            _invoice(2, 11, 50000, currency="NGN"),
        ]
        p = propose_payment_split(
            guardian_user_id=1,
            payment_amount=Decimal("100"),
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertTrue(any(r.startswith("currency_mismatch") for r in p.blocked_reasons))

    def test_fifo_allocation_oldest_first(self):
        children = _children((10, "Ada"))
        invs = [
            _invoice(1, 10, 200, due_date=date(2026, 4, 1)),
            _invoice(2, 10, 300, due_date=date(2026, 3, 1)),
            _invoice(3, 10, 100, due_date=date(2026, 5, 1)),
        ]
        p = propose_payment_split(
            guardian_user_id=1,
            payment_amount=Decimal("400"),
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        # Invoice 2 (March, $300) should be cleared first, then $100 of #1.
        self.assertEqual(p.lines[0].invoice_id, 2)
        self.assertEqual(p.lines[0].allocated_amount, Decimal("300"))
        self.assertEqual(p.lines[1].invoice_id, 1)
        self.assertEqual(p.lines[1].allocated_amount, Decimal("100"))
        self.assertEqual(p.total_proposed, Decimal("400"))
        self.assertEqual(p.leftover, Decimal("0"))

    def test_partial_payment_leaves_leftover(self):
        children = _children((10, "Ada"))
        invs = [_invoice(1, 10, 100)]
        p = propose_payment_split(
            guardian_user_id=1,
            payment_amount=Decimal("250"),
            children_runner=lambda uid: children,
            balance_runner=lambda ids: invs,
        )
        self.assertEqual(p.total_proposed, Decimal("100"))
        self.assertEqual(p.leftover, Decimal("150"))


class SerializationTests(SimpleTestCase):

    def test_summary_as_dict_keys_present(self):
        s = aggregate_family_balance(
            guardian_user_id=1,
            children_runner=lambda uid: _children((10, "Ada")),
            balance_runner=lambda ids: [_invoice(1, 10, 50)],
        )
        d = s.as_dict()
        self.assertIn("family_total_open_balance", d)
        self.assertIn("child_rows", d)
        self.assertEqual(d["child_rows"][0]["display_name"], "Ada")
