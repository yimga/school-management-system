"""Live HTTP gateway paths (mocked — no network in CI)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.finance.gateways.flutterwave import FlutterwaveGateway
from apps.finance.gateways.mtn_momo import MTNMoMoGateway
from apps.finance.gateways.paystack import PaystackGateway


class _School:
    pk = 1


class GatewayLiveHttpTests(SimpleTestCase):
    def test_paystack_initialize_live_http(self):
        cfg = {
            "secret_key": "sk_test_x",
            "default_payer_email": "parent@school.test",
        }
        gw = PaystackGateway(_School(), cfg)
        with patch(
            "apps.finance.gateways.paystack.http_post_json",
            return_value=(
                200,
                {
                    "status": True,
                    "data": {
                        "reference": "ref-001",
                        "authorization_url": "https://checkout.paystack.com/abc",
                        "access_code": "code",
                    },
                },
            ),
        ) as post:
            result = gw.initiate(
                Decimal("1500.00"),
                "NGN",
                "ref-001",
                payer_email="parent@school.test",
            )
        post.assert_called_once()
        self.assertTrue(result.success)
        self.assertEqual(result.transaction_id, "ref-001")
        self.assertIn("authorization_url", result.raw_response or {})

    def test_flutterwave_initialize_live_http(self):
        cfg = {
            "secret_key": "FLWSECK_TEST-xxx",
            "default_payer_email": "parent@school.test",
            "redirect_url": "https://school.test/callback",
        }
        gw = FlutterwaveGateway(_School(), cfg)
        with patch(
            "apps.finance.gateways.flutterwave.http_post_json",
            return_value=(
                200,
                {
                    "status": "success",
                    "data": {
                        "tx_ref": "flw-ref-1",
                        "link": "https://flutterwave.com/pay/flw-ref-1",
                    },
                },
            ),
        ):
            result = gw.initiate(
                Decimal("250.00"),
                "NGN",
                "flw-ref-1",
                payer_email="parent@school.test",
            )
        self.assertTrue(result.success)
        self.assertEqual(result.transaction_id, "flw-ref-1")
        self.assertIn("payment_url", result.raw_response or {})

    def test_mtn_momo_requesttopay_live_http(self):
        cfg = {
            "api_user": "user",
            "api_key": "token",
            "subscription_key": "sub-key",
            "target_environment": "sandbox",
        }
        gw = MTNMoMoGateway(_School(), cfg)
        with patch(
            "apps.finance.gateways.mtn_momo.http_post_json",
            return_value=(202, {}),
        ):
            result = gw.initiate(
                Decimal("5000"),
                "XAF",
                "fee-ref-9",
                payer_phone="237670000000",
                description="Tuition",
            )
        self.assertTrue(result.success)
        self.assertIn("polling_url", result.raw_response or {})

    def test_mtn_momo_check_status_live_http(self):
        cfg = {
            "api_key": "token",
            "subscription_key": "sub-key",
        }
        gw = MTNMoMoGateway(_School(), cfg)
        with patch(
            "apps.finance.gateways.mtn_momo.http_get_json",
            return_value=(200, {"status": "SUCCESSFUL"}),
        ):
            result = gw.check_status("abc-ref-id")
        self.assertTrue(result.success)

    def test_paystack_initialize_verify_round_trip(self):
        cfg = {"secret_key": "sk_test_x", "default_payer_email": "parent@school.test"}
        gw = PaystackGateway(_School(), cfg)
        with patch(
            "apps.finance.gateways.paystack.http_post_json",
            return_value=(
                200,
                {
                    "status": True,
                    "data": {
                        "reference": "ref-round",
                        "authorization_url": "https://checkout.paystack.com/abc",
                    },
                },
            ),
        ):
            init = gw.initiate(
                Decimal("1000.00"),
                "NGN",
                "ref-round",
                payer_email="parent@school.test",
            )
        self.assertTrue(init.success)
        with patch(
            "apps.finance.gateways.paystack.http_get_json",
            return_value=(
                200,
                {
                    "status": True,
                    "data": {"status": "success", "reference": "ref-round"},
                },
            ),
        ) as verify_get:
            verified = gw.check_status("ref-round")
        verify_get.assert_called_once()
        self.assertTrue(verified.success)

    def test_flutterwave_initialize_verify_round_trip(self):
        # redirect_url is REQUIRED by Flutterwave's /payments call. Without it this
        # test never reached the HTTP branch at all: the old `if email and redirect:`
        # was False, http_post_json (patched below) was never invoked, and the test
        # passed only via the fake-success fallthrough it was meant to be proving.
        # The mock was decorative. Supplying redirect_url makes the round trip real.
        cfg = {
            "secret_key": "FLWSECK_TEST-xxx",
            "default_payer_email": "parent@school.test",
            "redirect_url": "https://school.test/pay/return",
        }
        gw = FlutterwaveGateway(_School(), cfg)
        with patch(
            "apps.finance.gateways.flutterwave.http_post_json",
            return_value=(
                200,
                {
                    "status": "success",
                    "data": {"tx_ref": "flw-round", "link": "https://flutterwave.com/pay/x"},
                },
            ),
        ):
            init = gw.initiate(
                Decimal("100.00"),
                "NGN",
                "flw-round",
                payer_email="parent@school.test",
            )
        self.assertTrue(init.success)
        with patch(
            "apps.finance.gateways.flutterwave.http_get_json",
            return_value=(
                200,
                {
                    "status": "success",
                    "data": {"status": "successful", "tx_ref": "flw-round"},
                },
            ),
        ):
            verified = gw.check_status("flw-round")
        self.assertTrue(verified.success)

    def test_stub_only_skips_http(self):
        cfg = {"secret_key": "sk_test_x", "stub_only": True}
        gw = PaystackGateway(_School(), cfg)
        with patch("apps.finance.gateways.paystack.http_post_json") as post:
            result = gw.initiate(
                Decimal("10"),
                "NGN",
                "r1",
                payer_email="a@b.test",
            )
        post.assert_not_called()
        self.assertTrue(result.success)
        self.assertTrue(str(result.transaction_id or "").startswith("paystack_"))
