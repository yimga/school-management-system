"""Optional live PSP sandbox probes — runs only when CI secrets + RMC_PSP_SANDBOX_LIVE=1."""

from __future__ import annotations

import os
import unittest
from decimal import Decimal
from uuid import uuid4

from django.test import SimpleTestCase

from apps.finance.gateways.flutterwave import FlutterwaveGateway
from apps.finance.gateways.paystack import PaystackGateway


def _live_enabled() -> bool:
    if os.environ.get("RMC_PSP_SANDBOX_LIVE") != "1":
        return False
    return bool(
        os.environ.get("PAYSTACK_SECRET_KEY")
        or os.environ.get("FLUTTERWAVE_SECRET_KEY")
    )


@unittest.skipUnless(_live_enabled(), "Set RMC_PSP_SANDBOX_LIVE=1 and PSP sandbox secrets")
class PSPSandboxLiveTests(SimpleTestCase):
    """Non-destructive initialize calls against vendor sandbox APIs."""

    def test_paystack_sandbox_initialize_charge(self):
        secret = (os.environ.get("PAYSTACK_SECRET_KEY") or "").strip()
        self.assertTrue(secret.startswith("sk_test_") or secret.startswith("sk_live_"))
        gw = PaystackGateway(
            type("_School", (), {"pk": 1})(),
            {
                "secret_key": secret,
                "default_payer_email": os.environ.get(
                    "PAYSTACK_TEST_EMAIL", "sandbox-parent@runmycampus.test"
                ),
            },
        )
        ref = f"rmc-ci-{uuid4().hex[:12]}"
        result = gw.initiate(
            Decimal("100.00"),
            "NGN",
            ref,
            payer_email=os.environ.get(
                "PAYSTACK_TEST_EMAIL", "sandbox-parent@runmycampus.test"
            ),
        )
        self.assertTrue(result.success, result.message)
        self.assertIn("authorization_url", result.raw_response or {})

    def test_flutterwave_sandbox_initialize_charge(self):
        secret = (os.environ.get("FLUTTERWAVE_SECRET_KEY") or "").strip()
        if not secret:
            self.skipTest("FLUTTERWAVE_SECRET_KEY not set")
        self.assertIn("TEST", secret.upper())
        gw = FlutterwaveGateway(
            type("_School", (), {"pk": 1})(),
            {
                "secret_key": secret,
                "default_payer_email": os.environ.get(
                    "FLUTTERWAVE_TEST_EMAIL", "sandbox-parent@runmycampus.test"
                ),
                "redirect_url": "https://runmycampus.com/payments/callback/",
            },
        )
        ref = f"rmc-ci-{uuid4().hex[:12]}"
        result = gw.initiate(
            Decimal("100.00"),
            "NGN",
            ref,
            payer_email=os.environ.get(
                "FLUTTERWAVE_TEST_EMAIL", "sandbox-parent@runmycampus.test"
            ),
        )
        self.assertTrue(result.success, result.message)
        raw = result.raw_response or {}
        self.assertTrue(raw.get("payment_url") or raw.get("link"))
