"""Manual fallback rail runtime tests (batch 1506 audit closure)."""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.payment_rail_adapter import (
    ManualFallbackRail,
    PaymentIntent,
    PaymentRailRegistry,
    PaymentRailUnavailableError,
    register_manual_fallback,
    registry,
)


class ManualFallbackRuntimeTests(SimpleTestCase):
    def setUp(self) -> None:
        registry().clear()

    def test_manual_fallback_handles_any_currency(self) -> None:
        rail = ManualFallbackRail()
        intent = PaymentIntent(
            tenant_id="t",
            currency="ZWL",  # weird currency
            amount=Decimal("100"),
            idempotency_key="zwl-1",
        )
        result = rail.authorize(intent)
        self.assertTrue(result.success)
        self.assertEqual(result.rail_id, "manual-cash")

    def test_register_manual_fallback_exposes_default_registry(self) -> None:
        register_manual_fallback()
        rails = [r.rail_id for r in registry().rails()]
        self.assertIn("manual-cash", rails)

    def test_registry_without_fallback_rejects_unknown_currency(self) -> None:
        reg = PaymentRailRegistry()
        reg.register(ManualFallbackRail(rail_id="usd-only", currencies=("USD",)))
        intent = PaymentIntent(
            tenant_id="t",
            currency="EUR",
            amount=Decimal("1.00"),
            idempotency_key="eur-1",
        )
        with self.assertRaises(PaymentRailUnavailableError):
            reg.authorize(intent)

    def test_fallback_webhook_signature_round_trip(self) -> None:
        rail = ManualFallbackRail(shared_secret=b"sek")
        body = b'{"event":"refund"}'
        sig = hmac.new(b"sek", body, hashlib.sha256).hexdigest()
        self.assertTrue(rail.verify_webhook_signature(payload=body, signature_header=sig))

    def test_fallback_webhook_rejects_tampered_payload(self) -> None:
        rail = ManualFallbackRail(shared_secret=b"sek")
        body = b'{"event":"refund"}'
        sig = hmac.new(b"sek", body, hashlib.sha256).hexdigest()
        # Tamper payload
        self.assertFalse(rail.verify_webhook_signature(payload=b'{"event":"steal"}', signature_header=sig))

    def test_fallback_webhook_rejects_blank_secret(self) -> None:
        rail = ManualFallbackRail()  # no secret
        self.assertFalse(rail.verify_webhook_signature(payload=b"x", signature_header="x"))
