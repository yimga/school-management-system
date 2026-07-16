"""Live-configured gateways must FAIL CLOSED, never report phantom success.

Found by the PROMPT B audit fleet (2026-07-16). All three gateways that do real
network I/O shared one shape::

    if secret and not stub_only:        # live-configured
        if email:                       # required runtime field
            ... real HTTP ...
            return GatewayResult(success=False, ...)   # only on HTTP error
    return GatewayResult(success=True, transaction_id=f"paystack_{reference}")

When the gateway was live-configured but a required *runtime* field was absent,
the HTTP call was skipped and control fell through to the success return. The
caller received ``success=True`` and a fabricated transaction_id for money that
never left the process. A misconfigured tenant would record a successful payment
that was never requested -- a money-integrity bug, not a cosmetic one.

The three modes that must stay distinct:

* unconfigured (no secret / api keys)  -> success=False "not_configured" (pre-existing)
* ``stub_only=True``                   -> success=True, DELIBERATE stub mode; these
  tests pin that so the fix cannot be "fixed" by breaking stub callers
* live-configured + missing field      -> success=False (the fix)

No network is touched: every case here returns before any HTTP call, which is
exactly the branch that used to lie.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.gateways.flutterwave import FlutterwaveGateway
from apps.finance.gateways.mtn_momo import MTNMoMoGateway
from apps.finance.gateways.paystack import PaystackGateway


class PaystackFailClosedTests(SimpleTestCase):
    def test_live_configured_without_payer_email_fails_closed(self):
        gw = PaystackGateway(None, config={"secret_key": "sk_live_realsecret"})
        result = gw.initiate(
            amount=Decimal("5000.00"), currency="NGN", reference="ref-no-email"
        )
        self.assertFalse(
            result.success,
            "live-configured Paystack with no payer email must NOT report success "
            "for a charge it never sent",
        )
        self.assertIsNone(
            result.transaction_id,
            "a charge that was never sent must not hand back a transaction id",
        )

    def test_stub_only_still_succeeds(self):
        # stub_only is a deliberate mode; the fail-closed fix must not break it.
        gw = PaystackGateway(None, config={"secret_key": "sk_test", "stub_only": True})
        result = gw.initiate(
            amount=Decimal("10.00"), currency="NGN", reference="ref-stub"
        )
        self.assertTrue(result.success)

    def test_unconfigured_still_fails_closed(self):
        gw = PaystackGateway(None, config={})
        result = gw.initiate(amount=Decimal("10.00"), currency="NGN", reference="r")
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")


class FlutterwaveFailClosedTests(SimpleTestCase):
    def test_live_configured_without_email_or_redirect_fails_closed(self):
        gw = FlutterwaveGateway(None, config={"secret_key": "FLWSECK-live"})
        result = gw.initiate(
            amount=Decimal("2500.00"), currency="NGN", reference="ref-no-fields"
        )
        self.assertFalse(
            result.success,
            "live-configured Flutterwave missing payer_email/redirect_url must not "
            "report success for a charge it never sent",
        )
        self.assertIsNone(result.transaction_id)

    def test_live_configured_with_email_but_no_redirect_fails_closed(self):
        # Partial config is the realistic case: /payments needs BOTH.
        gw = FlutterwaveGateway(None, config={"secret_key": "FLWSECK-live"})
        result = gw.initiate(
            amount=Decimal("2500.00"),
            currency="NGN",
            reference="ref-partial",
            payer_email="parent@example.com",
        )
        self.assertFalse(result.success)
        self.assertIn("redirect_url", result.raw_response.get("missing", []))

    def test_stub_only_still_succeeds(self):
        gw = FlutterwaveGateway(None, config={"secret_key": "x", "stub_only": True})
        result = gw.initiate(
            amount=Decimal("10.00"), currency="NGN", reference="ref-stub"
        )
        self.assertTrue(result.success)


class MtnMomoFailClosedTests(SimpleTestCase):
    _LIVE = {
        "api_user": "u-123",
        "api_key": "k-456",
        "subscription_key": "s-789",
    }

    def test_live_configured_without_payer_phone_fails_closed(self):
        gw = MTNMoMoGateway(None, config=dict(self._LIVE))
        result = gw.initiate(
            amount=Decimal("15000"), currency="XAF", reference="ref-no-phone"
        )
        self.assertFalse(
            result.success,
            "live-configured MTN MoMo with no payer phone must not report success "
            "for a collection it never sent",
        )
        self.assertIsNone(result.transaction_id)

    def test_stub_only_still_succeeds(self):
        gw = MTNMoMoGateway(None, config=dict(self._LIVE, stub_only=True))
        result = gw.initiate(
            amount=Decimal("15000"), currency="XAF", reference="ref-stub"
        )
        self.assertTrue(result.success)

    def test_unconfigured_still_fails_closed(self):
        gw = MTNMoMoGateway(None, config={})
        result = gw.initiate(amount=Decimal("100"), currency="XAF", reference="r")
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")
