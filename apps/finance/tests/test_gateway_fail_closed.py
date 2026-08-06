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
from apps.finance.gateways.mpesa_daraja import MpesaDarajaGateway
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


class MpesaDarajaFailClosedTests(SimpleTestCase):
    _LIVE = {
        "consumer_key": "ck-live",
        "consumer_secret": "cs-live",
        "shortcode": "174379",
        "passkey": "passkey-live",
    }

    def test_live_configured_without_payer_phone_fails_closed(self):
        gw = MpesaDarajaGateway(None, config=dict(self._LIVE))
        result = gw.initiate(
            amount=Decimal("500"), currency="KES", reference="ref-no-phone"
        )
        self.assertFalse(result.success)
        self.assertIsNone(result.transaction_id)

    def test_stub_only_still_succeeds(self):
        gw = MpesaDarajaGateway(None, config=dict(self._LIVE, stub_only=True))
        result = gw.initiate(
            amount=Decimal("500"), currency="KES", reference="ref-stub"
        )
        self.assertTrue(result.success)

    def test_unconfigured_still_fails_closed(self):
        gw = MpesaDarajaGateway(None, config={})
        result = gw.initiate(amount=Decimal("100"), currency="KES", reference="r")
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")

    def test_unsupported_currency_fails_closed(self):
        gw = MpesaDarajaGateway(None, config=dict(self._LIVE, stub_only=True))
        result = gw.initiate(
            amount=Decimal("10"), currency="USD", reference="ref-usd"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "unsupported_currency")


class RazorpayFailClosedTests(SimpleTestCase):
    """UPI rail: live keys must never fabricate success without HTTP."""

    def test_unconfigured_fails(self):
        from apps.finance.gateways.razorpay import RazorpayGateway

        gw = RazorpayGateway(None, config={})
        result = gw.initiate(amount=Decimal("100"), currency="INR", reference="r")
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")

    def test_stub_only_still_succeeds(self):
        from apps.finance.gateways.razorpay import RazorpayGateway

        gw = RazorpayGateway(
            None,
            config={"key_id": "rzp_test", "key_secret": "secret", "stub_only": True},
        )
        result = gw.initiate(amount=Decimal("100"), currency="INR", reference="stub")
        self.assertTrue(result.success)
        self.assertTrue(str(result.transaction_id or "").startswith("razorpay_"))

    def test_live_http_error_fails_closed(self):
        from unittest.mock import patch

        from apps.finance.gateways.razorpay import RazorpayGateway

        gw = RazorpayGateway(
            None, config={"key_id": "rzp_live", "key_secret": "sk_live"}
        )
        with patch(
            "apps.finance.gateways.razorpay.http_post_json",
            return_value=(401, {"error": {"description": "auth"}}),
        ):
            result = gw.initiate(
                amount=Decimal("250.00"), currency="INR", reference="ref-fail"
            )
        self.assertFalse(result.success)
        self.assertIsNone(result.transaction_id)


class MercadoPagoFailClosedTests(SimpleTestCase):
    """Pix / LATAM rail: live token must never fabricate success without HTTP."""

    def test_unconfigured_fails(self):
        from apps.finance.gateways.mercado_pago import MercadoPagoGateway

        gw = MercadoPagoGateway(None, config={})
        result = gw.initiate(amount=Decimal("50"), currency="BRL", reference="r")
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")

    def test_stub_only_still_succeeds(self):
        from apps.finance.gateways.mercado_pago import MercadoPagoGateway

        gw = MercadoPagoGateway(
            None, config={"access_token": "APP_USR-x", "stub_only": True}
        )
        result = gw.initiate(amount=Decimal("50"), currency="BRL", reference="stub")
        self.assertTrue(result.success)
        self.assertTrue(str(result.transaction_id or "").startswith("mp_"))

    def test_live_http_error_fails_closed(self):
        from unittest.mock import patch

        from apps.finance.gateways.mercado_pago import MercadoPagoGateway

        gw = MercadoPagoGateway(None, config={"access_token": "APP_USR-live"})
        with patch(
            "apps.finance.gateways.mercado_pago.http_post_json",
            return_value=(500, {"message": "boom"}),
        ):
            result = gw.initiate(
                amount=Decimal("80.00"), currency="BRL", reference="ref-fail"
            )
        self.assertFalse(result.success)
        self.assertIsNone(result.transaction_id)


# ---------------------------------------------------------------------------
# 2026-08-05: the three rails that had NO live HTTP initiation at all
# (orange_money / dlocal / pesapal) previously fabricated success=True + a
# synthetic transaction_id the moment they were config-complete — a
# collection the payer was never prompted for, a pending payment that could
# never settle. They now fail closed unless stub_only is set. Same three
# distinct modes as the rails above.
# ---------------------------------------------------------------------------


class OrangeMoneyFailClosedTests(SimpleTestCase):
    _LIVE = {"client_id": "c-1", "client_secret": "s-1", "merchant_key": "m-1"}

    def test_live_configured_without_real_http_fails_closed(self):
        from apps.finance.gateways.orange_money import OrangeMoneyGateway

        gw = OrangeMoneyGateway(None, config=dict(self._LIVE))
        result = gw.initiate(
            amount=Decimal("15000"), currency="XAF", reference="ref-live"
        )
        self.assertFalse(
            result.success,
            "live-configured Orange Money must not fabricate success for a "
            "collection it never sent",
        )
        self.assertIsNone(result.transaction_id)
        self.assertEqual(
            result.raw_response.get("status"), "initiation_not_implemented"
        )

    def test_stub_only_still_succeeds(self):
        from apps.finance.gateways.orange_money import OrangeMoneyGateway

        gw = OrangeMoneyGateway(None, config=dict(self._LIVE, stub_only=True))
        result = gw.initiate(
            amount=Decimal("15000"), currency="XAF", reference="ref-stub"
        )
        self.assertTrue(result.success)
        self.assertTrue(str(result.transaction_id or "").startswith("orange_"))

    def test_unconfigured_still_fails_closed(self):
        from apps.finance.gateways.orange_money import OrangeMoneyGateway

        gw = OrangeMoneyGateway(None, config={})
        result = gw.initiate(amount=Decimal("100"), currency="XAF", reference="r")
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")


class DlocalFailClosedTests(SimpleTestCase):
    _LIVE = {"api_key": "k-1", "secret_key": "s-1"}

    def test_live_configured_without_real_http_fails_closed(self):
        from apps.finance.gateways.dlocal import DlocalGateway

        gw = DlocalGateway(None, config=dict(self._LIVE))
        result = gw.initiate(
            amount=Decimal("50.00"), currency="BRL", reference="ref-live"
        )
        self.assertFalse(result.success)
        self.assertIsNone(result.transaction_id)
        self.assertEqual(
            result.raw_response.get("status"), "initiation_not_implemented"
        )

    def test_stub_only_still_succeeds(self):
        from apps.finance.gateways.dlocal import DlocalGateway

        gw = DlocalGateway(None, config=dict(self._LIVE, stub_only=True))
        result = gw.initiate(
            amount=Decimal("50.00"), currency="BRL", reference="ref-stub"
        )
        self.assertTrue(result.success)
        self.assertTrue(str(result.transaction_id or "").startswith("dlocal_"))

    def test_unconfigured_still_fails_closed(self):
        from apps.finance.gateways.dlocal import DlocalGateway

        gw = DlocalGateway(None, config={})
        result = gw.initiate(amount=Decimal("100"), currency="BRL", reference="r")
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")


class PesapalFailClosedTests(SimpleTestCase):
    _LIVE = {"consumer_key": "ck-1", "consumer_secret": "cs-1"}

    def test_live_configured_without_real_http_fails_closed(self):
        from apps.finance.gateways.pesapal import PesapalGateway

        gw = PesapalGateway(None, config=dict(self._LIVE))
        result = gw.initiate(
            amount=Decimal("500"), currency="KES", reference="ref-live"
        )
        self.assertFalse(result.success)
        self.assertIsNone(result.transaction_id)
        self.assertEqual(
            result.raw_response.get("status"), "initiation_not_implemented"
        )

    def test_stub_only_still_succeeds(self):
        from apps.finance.gateways.pesapal import PesapalGateway

        gw = PesapalGateway(None, config=dict(self._LIVE, stub_only=True))
        result = gw.initiate(
            amount=Decimal("500"), currency="KES", reference="ref-stub"
        )
        self.assertTrue(result.success)
        self.assertTrue(str(result.transaction_id or "").startswith("pesapal_"))

    def test_unconfigured_still_fails_closed(self):
        from apps.finance.gateways.pesapal import PesapalGateway

        gw = PesapalGateway(None, config={})
        result = gw.initiate(amount=Decimal("100"), currency="KES", reference="r")
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")
