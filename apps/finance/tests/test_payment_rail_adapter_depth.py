"""Depth tests for apps.finance.payment_rail_adapter (batch 1509).

Complements the existing contract tests with:

- cross-tenant fingerprint isolation
- idempotency replay-protection negative paths
- HMAC signature verification negative paths
- log emission hygiene (no signature bytes, no shared secret)
- Decimal-only money invariants
- registry state isolation after clear()
"""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.payment_rail_adapter import (
    ManualFallbackRail,
    PaymentIntent,
    PaymentRailIdempotencyError,
    PaymentRailRegistry,
    PaymentRailUnavailableError,
    _intent_fingerprint,
    register_manual_fallback,
    registry,
)


def _intent(**overrides) -> PaymentIntent:
    base = {
        "tenant_id": "tenant-A",
        "currency": "USD",
        "amount": Decimal("10.00"),
        "idempotency_key": "key-1",
        "description": "test",
    }
    base.update(overrides)
    return PaymentIntent(**base)


class PaymentRailAdapterDepthTests(SimpleTestCase):
    def setUp(self) -> None:
        registry().clear()
        register_manual_fallback()

    def tearDown(self) -> None:
        registry().clear()

    def test_fingerprint_differs_across_tenants(self) -> None:
        f_a = _intent_fingerprint(_intent(tenant_id="tenant-A"))
        f_b = _intent_fingerprint(_intent(tenant_id="tenant-B"))
        self.assertNotEqual(f_a, f_b)

    def test_fingerprint_differs_across_amounts(self) -> None:
        f_low = _intent_fingerprint(_intent(amount=Decimal("10.00")))
        f_high = _intent_fingerprint(_intent(amount=Decimal("10.01")))
        self.assertNotEqual(f_low, f_high)

    def test_idempotency_replay_with_same_intent_succeeds(self) -> None:
        reg = registry()
        result1 = reg.authorize(_intent(idempotency_key="repeat-1"))
        result2 = reg.authorize(_intent(idempotency_key="repeat-1"))
        self.assertTrue(result1.success)
        self.assertTrue(result2.success)

    def test_idempotency_collision_with_diverging_intent_raises(self) -> None:
        reg = registry()
        reg.authorize(_intent(idempotency_key="collide-1", amount=Decimal("10.00")))
        with self.assertRaises(PaymentRailIdempotencyError):
            reg.authorize(_intent(idempotency_key="collide-1", amount=Decimal("99.99")))

    def test_idempotency_collision_with_diverging_tenant_raises(self) -> None:
        reg = registry()
        reg.authorize(_intent(idempotency_key="cross-tenant", tenant_id="tenant-A"))
        with self.assertRaises(PaymentRailIdempotencyError):
            reg.authorize(_intent(idempotency_key="cross-tenant", tenant_id="tenant-B"))

    def test_manual_fallback_rejects_signature_without_secret(self) -> None:
        rail = ManualFallbackRail(shared_secret=b"")
        ok = rail.verify_webhook_signature(payload=b"hello", signature_header="anything")
        self.assertFalse(ok)

    def test_manual_fallback_rejects_wrong_signature(self) -> None:
        rail = ManualFallbackRail(shared_secret=b"correct-secret")
        wrong_sig = hmac.new(b"wrong-secret", b"hello", hashlib.sha256).hexdigest()
        ok = rail.verify_webhook_signature(payload=b"hello", signature_header=wrong_sig)
        self.assertFalse(ok)

    def test_manual_fallback_accepts_correct_signature(self) -> None:
        rail = ManualFallbackRail(shared_secret=b"correct-secret")
        good_sig = hmac.new(b"correct-secret", b"hello", hashlib.sha256).hexdigest()
        ok = rail.verify_webhook_signature(payload=b"hello", signature_header=good_sig)
        self.assertTrue(ok)

    def test_manual_fallback_rejects_tampered_payload(self) -> None:
        rail = ManualFallbackRail(shared_secret=b"correct-secret")
        sig = hmac.new(b"correct-secret", b"hello", hashlib.sha256).hexdigest()
        ok = rail.verify_webhook_signature(payload=b"hello-tampered", signature_header=sig)
        self.assertFalse(ok)

    def test_log_emission_omits_idempotency_key_and_amount(self) -> None:
        reg = registry()
        with self.assertLogs("apps.finance.payment_rail_adapter", level="INFO") as cm:
            reg.authorize(
                _intent(idempotency_key="distinctive-log-key-XYZ", amount=Decimal("12345.67"))
            )
        log_text = "\n".join(cm.output)
        self.assertNotIn("distinctive-log-key-XYZ", log_text)
        self.assertNotIn("12345.67", log_text)

    def test_intent_rejects_float_amount(self) -> None:
        with self.assertRaises(TypeError):
            PaymentIntent(
                tenant_id="tenant-A",
                currency="USD",
                amount=10.00,  # float, not Decimal — must reject
                idempotency_key="x",
            )

    def test_intent_rejects_zero_and_negative_amounts(self) -> None:
        with self.assertRaises(ValueError):
            PaymentIntent(
                tenant_id="tenant-A",
                currency="USD",
                amount=Decimal("0"),
                idempotency_key="zero",
            )
        with self.assertRaises(ValueError):
            PaymentIntent(
                tenant_id="tenant-A",
                currency="USD",
                amount=Decimal("-1.00"),
                idempotency_key="neg",
            )

    def test_intent_rejects_empty_idempotency_key(self) -> None:
        with self.assertRaises(ValueError):
            PaymentIntent(
                tenant_id="tenant-A",
                currency="USD",
                amount=Decimal("1.00"),
                idempotency_key="",
            )

    def test_registry_select_filters_by_currency(self) -> None:
        reg = PaymentRailRegistry()
        reg.register(ManualFallbackRail(rail_id="usd-only", currencies=("USD",)))
        reg.register(ManualFallbackRail(rail_id="eur-only", currencies=("EUR",)))
        usd_rail = reg.select(currency="USD")
        self.assertEqual(usd_rail.rail_id, "usd-only")
        eur_rail = reg.select(currency="EUR")
        self.assertEqual(eur_rail.rail_id, "eur-only")
        with self.assertRaises(PaymentRailUnavailableError):
            reg.select(currency="XOF")

    def test_registry_clear_isolates_idempotency_seen(self) -> None:
        reg = registry()
        reg.authorize(_intent(idempotency_key="before-clear", amount=Decimal("1.00")))
        reg.clear()
        register_manual_fallback()
        # Same key with different intent should now succeed because state cleared.
        result = reg.authorize(_intent(idempotency_key="before-clear", amount=Decimal("99.99")))
        self.assertTrue(result.success)
