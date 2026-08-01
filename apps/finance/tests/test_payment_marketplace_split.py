"""Collect-on-behalf remains disabled future scope."""

import os

from django.test import SimpleTestCase

from apps.finance.payment_marketplace_split import (
    PaymentSplitCounselRequiredError,
    counsel_token_configured,
    initiate_flutterwave_marketplace_split,
    initiate_paystack_subaccount_split,
)


class PaymentMarketplaceSplitTests(SimpleTestCase):
    def test_refuses_without_token(self):
        with self.assertRaises(PaymentSplitCounselRequiredError):
            initiate_paystack_subaccount_split(
                school_id=1, amount_minor=1000, subaccount_code="ACCT_1"
            )

    def test_environment_token_cannot_enable_collection_on_behalf(self):
        token = "test-counsel-token-1444"
        os.environ["SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN"] = token
        try:
            self.assertFalse(counsel_token_configured())
            with self.assertRaises(PaymentSplitCounselRequiredError):
                initiate_paystack_subaccount_split(
                    school_id=1,
                    amount_minor=500,
                    subaccount_code="ACCT_X",
                    counsel_token=token,
                )
            with self.assertRaises(PaymentSplitCounselRequiredError):
                initiate_flutterwave_marketplace_split(
                    school_id=1,
                    amount="10.00",
                    subaccount_id="SUB_1",
                    counsel_token=token,
                )
        finally:
            os.environ.pop("SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN", None)
