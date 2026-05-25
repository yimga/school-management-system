"""Payment idempotency runtime tests (batch 1506 audit closure)."""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.payment_rail_adapter import (
    ManualFallbackRail,
    PaymentIntent,
    PaymentRailIdempotencyError,
    PaymentRailRegistry,
)


class PaymentIdempotencyRuntimeTests(SimpleTestCase):
    def _reg(self) -> PaymentRailRegistry:
        r = PaymentRailRegistry()
        r.register(ManualFallbackRail())
        return r

    def test_same_intent_replay_returns_same_reference(self) -> None:
        reg = self._reg()
        intent = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("12.34"),
            idempotency_key="abc",
        )
        a = reg.authorize(intent)
        b = reg.authorize(intent)
        self.assertEqual(a.reference, b.reference)

    def test_diverging_amount_on_same_key_blocked(self) -> None:
        reg = self._reg()
        first = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("10.00"),
            idempotency_key="key-z",
        )
        diff = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("99.99"),
            idempotency_key="key-z",
        )
        reg.authorize(first)
        with self.assertRaises(PaymentRailIdempotencyError):
            reg.authorize(diff)

    def test_diverging_tenant_on_same_key_blocked(self) -> None:
        reg = self._reg()
        a = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("10.00"),
            idempotency_key="key-y",
        )
        b = PaymentIntent(
            tenant_id="t2",
            currency="USD",
            amount=Decimal("10.00"),
            idempotency_key="key-y",
        )
        reg.authorize(a)
        with self.assertRaises(PaymentRailIdempotencyError):
            reg.authorize(b)

    def test_different_keys_independent(self) -> None:
        reg = self._reg()
        a = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("1.00"),
            idempotency_key="k-a",
        )
        b = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("2.00"),
            idempotency_key="k-b",
        )
        ra = reg.authorize(a)
        rb = reg.authorize(b)
        self.assertNotEqual(ra.reference, rb.reference)

    def test_missing_idempotency_key_rejected_at_intent(self) -> None:
        with self.assertRaises(ValueError):
            PaymentIntent(
                tenant_id="t",
                currency="USD",
                amount=Decimal("1.00"),
                idempotency_key="",
            )
