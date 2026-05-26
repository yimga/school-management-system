"""Wave Q1+Q2 (v3.95.2 — 2026-05-26) — PSP live-creator + Stripe dynamic tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.billing.embedded_checkout import (
    CheckoutLineItem,
    CheckoutSessionRequest,
)
from apps.billing.embedded_checkout_psp_creators import (
    create_flutterwave_session,
    create_mtn_momo_session,
    create_orange_money_session,
    create_paystack_session,
    create_razorpay_session,
    get_live_creator,
    list_live_creators,
)


def _req(currency="NGN", phone="+237600000001", amount=100000):
    return CheckoutSessionRequest(
        tenant_id="t1",
        parent_email="parent@example.com",
        parent_phone=phone,
        line_items=(CheckoutLineItem(
            sku="X", description="Term 1", amount_minor=amount,
            currency=currency,
        ),),
        purpose="tuition_fee",
        student_reference="STU-1",
    )


class RegistryTests(SimpleTestCase):

    def test_5_psp_creators_registered(self):
        creators = list_live_creators()
        for psp in ("paystack", "flutterwave", "razorpay", "mtn_momo",
                     "orange_money"):
            self.assertIn(psp, creators)

    def test_get_unknown_returns_none(self):
        self.assertIsNone(get_live_creator("does-not-exist"))


class PaystackCreatorTests(SimpleTestCase):

    def test_missing_credentials_returns_error(self):
        # No tenant PSP config in test scope → creator returns credentials-
        # missing error (the dispatcher then falls through to next).
        result = create_paystack_session(_req(), "rmc_ck_x", 100000)
        self.assertFalse(result["ok"])
        self.assertIn("credentials missing", result["error"])

    def test_with_stubbed_poster_returns_ok(self):
        # Inject a fake HTTP poster + fake config. Mock paystack response.
        from unittest.mock import patch

        fake_response = {
            "ok": True,
            "data": {"status": True, "data": {
                "authorization_url": "https://checkout.paystack.com/abc",
                "access_code": "ac_123",
                "reference": "rmc_ck_x",
            }},
        }

        def fake_poster(url, payload, headers, *, auth=None):
            return fake_response

        with patch("apps.billing.embedded_checkout_psp_creators._tenant_psp_config",
                   return_value={"secret_key": "sk_test_xxx"}):
            result = create_paystack_session(
                _req(), "rmc_ck_x", 100000, http_post=fake_poster,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["hosted_url"], "https://checkout.paystack.com/abc")
        self.assertEqual(result["metadata"]["psp"], "paystack")


class FlutterwaveCreatorTests(SimpleTestCase):

    def test_missing_credentials_returns_error(self):
        result = create_flutterwave_session(_req(), "rmc_ck_x", 100000)
        self.assertFalse(result["ok"])

    def test_zero_decimal_xaf_keeps_minor_amount(self):
        from unittest.mock import patch

        captured = {}

        def fake_poster(url, payload, headers, *, auth=None):
            captured["payload"] = payload
            return {"ok": True, "data": {"data": {"link": "https://x"}}}

        with patch("apps.billing.embedded_checkout_psp_creators._tenant_psp_config",
                   return_value={"secret_key": "FLWSECK_TEST-x"}):
            create_flutterwave_session(
                _req(currency="XAF", amount=50000), "rmc_ck_x", 50000,
                http_post=fake_poster,
            )
        # XAF is zero-decimal → amount stays at minor value (50000), not divided.
        self.assertEqual(captured["payload"]["amount"], 50000)

    def test_usd_converts_minor_to_major(self):
        from unittest.mock import patch

        captured = {}

        def fake_poster(url, payload, headers, *, auth=None):
            captured["payload"] = payload
            return {"ok": True, "data": {"data": {"link": "https://x"}}}

        with patch("apps.billing.embedded_checkout_psp_creators._tenant_psp_config",
                   return_value={"secret_key": "FLWSECK_TEST-x"}):
            create_flutterwave_session(
                _req(currency="USD", amount=2500), "rmc_ck_x", 2500,
                http_post=fake_poster,
            )
        # USD: 2500 minor / 100 = 25.0 major.
        self.assertEqual(captured["payload"]["amount"], 25.0)


class RazorpayCreatorTests(SimpleTestCase):

    def test_missing_both_keys(self):
        result = create_razorpay_session(_req(currency="INR"), "rmc_ck_x", 100000)
        self.assertFalse(result["ok"])

    def test_with_full_creds_returns_ok(self):
        from unittest.mock import patch

        def fake_poster(url, payload, headers, *, auth=None):
            # Razorpay uses HTTP basic auth.
            self.assertEqual(auth, ("rzp_test_xxx", "secret_yyy"))
            return {"ok": True, "data": {"id": "order_NkXyz"}}

        with patch("apps.billing.embedded_checkout_psp_creators._tenant_psp_config",
                   return_value={"key_id": "rzp_test_xxx",
                                  "secret_key": "secret_yyy"}):
            result = create_razorpay_session(
                _req(currency="INR"), "rmc_ck_x", 100000,
                http_post=fake_poster,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["metadata"]["razorpay_order_id"], "order_NkXyz")


class MTNMoMoCreatorTests(SimpleTestCase):

    def test_missing_all_three_creds(self):
        result = create_mtn_momo_session(_req(currency="XAF"), "rmc_ck_x", 50000)
        self.assertFalse(result["ok"])
        self.assertIn("api_user", result["error"])

    def test_with_full_creds_returns_polling_url(self):
        from unittest.mock import patch

        with patch("apps.billing.embedded_checkout_psp_creators._tenant_psp_config",
                   return_value={"api_user": "x", "api_key": "y",
                                  "subscription_key": "z"}):
            result = create_mtn_momo_session(
                _req(currency="XAF"), "rmc_ck_x", 50000,
                http_post=lambda *_a, **_k: {"ok": True, "data": {}},
            )
        self.assertTrue(result["ok"])
        # MoMo uses USSD push, not a hosted URL.
        self.assertTrue(result["hosted_url"].startswith("runmycampus://"))
        self.assertIn("polling_url", result["metadata"])


class OrangeMoneyCreatorTests(SimpleTestCase):

    def test_missing_creds(self):
        result = create_orange_money_session(_req(currency="XOF"), "rmc_ck_x", 5000)
        self.assertFalse(result["ok"])

    def test_with_creds_extracts_payment_url(self):
        from unittest.mock import patch

        def fake_poster(url, payload, headers, *, auth=None):
            return {"ok": True, "data": {
                "payment_url": "https://webpay.orange.com/xyz",
                "pay_token": "tok_abc",
                "notif_token": "nt_xyz",
            }}

        with patch("apps.billing.embedded_checkout_psp_creators._tenant_psp_config",
                   return_value={"merchant_key": "m", "access_token": "t"}):
            result = create_orange_money_session(
                _req(currency="XOF"), "rmc_ck_x", 5000,
                http_post=fake_poster,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["hosted_url"], "https://webpay.orange.com/xyz")
        self.assertEqual(result["metadata"]["pay_token"], "tok_abc")


class StripeDynamicSessionTests(SimpleTestCase):

    def test_missing_config_returns_error(self):
        from unittest.mock import patch

        from apps.billing.embedded_checkout_stripe_dynamic import (
            create_stripe_dynamic_session,
        )

        with patch("apps.billing.stripe_checkout.get_active_stripe_processor_config",
                   return_value=None):
            result = create_stripe_dynamic_session(_req(currency="USD"),
                                                    "rmc_ck_x", 2500)
        self.assertFalse(result["ok"])
        self.assertIn("not active", result["error"])

    def test_with_stubbed_poster_builds_price_data(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from apps.billing.embedded_checkout_stripe_dynamic import (
            create_stripe_dynamic_session,
        )

        captured = {}
        cfg = SimpleNamespace(metadata={"secret_key": "sk_test_xxx"})

        def fake_form_post(url, params, headers):
            captured["url"] = url
            captured["params"] = params
            return (200, {"id": "cs_test_abc", "url": "https://checkout.stripe.com/abc"})

        with patch("apps.billing.stripe_checkout.get_active_stripe_processor_config",
                   return_value=cfg):
            result = create_stripe_dynamic_session(
                _req(currency="USD", amount=2500), "rmc_ck_x", 2500,
                http_post_form=fake_form_post,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["hosted_url"], "https://checkout.stripe.com/abc")
        # Confirm price_data was built (not a pre-created price).
        self.assertIn("line_items[0][price_data][currency]", captured["params"])
        self.assertEqual(captured["params"]["line_items[0][price_data][unit_amount]"], "2500")
