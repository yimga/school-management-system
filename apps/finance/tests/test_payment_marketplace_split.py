"""Counsel-gated payment splits (SFDP 1444)."""

import os
from django.test import SimpleTestCase, override_settings

from apps.finance.payment_marketplace_split import (
    PaymentSplitCounselRequiredError,
    initiate_flutterwave_marketplace_split,
    initiate_paystack_subaccount_split,
)


class PaymentMarketplaceSplitTests(SimpleTestCase):
    def test_refuses_without_counsel_token(self):
        with self.assertRaises(PaymentSplitCounselRequiredError):
            initiate_paystack_subaccount_split(
                school_id=1,
                amount_minor=1000,
                subaccount_code="ACCT_1",
                counsel_token=None,
            )

    @override_settings()
    def test_allows_with_matching_env_token(self):
        token = "test-counsel-token-1444"
        with override_settings():
            os.environ["SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN"] = token
            try:
                result = initiate_paystack_subaccount_split(
                    school_id=1,
                    amount_minor=500,
                    subaccount_code="ACCT_X",
                    counsel_token=token,
                )
                self.assertTrue(result.allowed)
                flw = initiate_flutterwave_marketplace_split(
                    school_id=1,
                    amount="10.00",
                    subaccount_id="SUB_1",
                    counsel_token=token,
                )
                self.assertEqual(flw.provider, "flutterwave")
            finally:
                os.environ.pop("SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN", None)
