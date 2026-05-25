"""Runtime tests for apps.finance.payment_rail_adapter (batch 1493)."""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.payment_rail_adapter import (
    ManualFallbackRail,
    PaymentIntent,
    PaymentRailIdempotencyError,
    PaymentRailRegistry,
    PaymentRailUnavailableError,
    register_manual_fallback,
    registry,
)


class PaymentRailAdapterRuntimeTests(SimpleTestCase):
    def setUp(self) -> None:
        registry().clear()

    def test_select_returns_currency_compatible_rail(self) -> None:
        reg = PaymentRailRegistry()
        reg.register(ManualFallbackRail(rail_id="usd-only", currencies=("USD",)))
        reg.register(ManualFallbackRail(rail_id="any"))
        rail = reg.select(currency="USD")
        self.assertEqual(rail.rail_id, "usd-only")

    def test_select_raises_when_no_enabled_rail(self) -> None:
        reg = PaymentRailRegistry()
        with self.assertRaises(PaymentRailUnavailableError):
            reg.select(currency="USD")

    def test_idempotency_key_blocks_diverging_intent(self) -> None:
        reg = PaymentRailRegistry()
        reg.register(ManualFallbackRail())
        intent_a = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("12.50"),
            idempotency_key="req-1",
        )
        intent_b = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("99.00"),  # different amount, same key
            idempotency_key="req-1",
        )
        reg.authorize(intent_a)
        with self.assertRaises(PaymentRailIdempotencyError):
            reg.authorize(intent_b)

    def test_idempotency_key_replay_returns_success(self) -> None:
        reg = PaymentRailRegistry()
        reg.register(ManualFallbackRail())
        intent = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("12.50"),
            idempotency_key="req-1",
        )
        first = reg.authorize(intent)
        second = reg.authorize(intent)
        self.assertEqual(first.reference, second.reference)

    def test_manual_fallback_webhook_signature_constant_time(self) -> None:
        rail = ManualFallbackRail(shared_secret=b"secret")
        import hashlib
        import hmac
        body = b'{"event":"ping"}'
        sig = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(rail.verify_webhook_signature(payload=body, signature_header=sig))
        self.assertFalse(rail.verify_webhook_signature(payload=body, signature_header="x" * 64))

    def test_register_manual_fallback_attaches_to_default_registry(self) -> None:
        register_manual_fallback()
        intent = PaymentIntent(
            tenant_id="t1",
            currency="USD",
            amount=Decimal("5.00"),
            idempotency_key="mf-1",
        )
        result = registry().authorize(intent)
        self.assertTrue(result.success)
        self.assertEqual(result.rail_id, "manual-cash")
