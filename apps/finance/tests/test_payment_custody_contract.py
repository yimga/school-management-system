from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.gateways.registry import get_platform_fee
from apps.finance.payment_custody_contract import tenant_payment_boundary


class PaymentCustodyContractTests(SimpleTestCase):
    def test_current_tenant_fee_boundary_has_no_platform_custody(self):
        self.assertEqual(
            tenant_payment_boundary(),
            {
                "platform_subscription_owner": "runmycampus",
                "tenant_fee_merchant_of_record": "tenant",
                "tenant_gateway_credential_owner": "tenant",
                "tenant_funds_settlement_owner": "tenant",
                "platform_collects_tenant_funds": False,
                "platform_splits_tenant_funds": False,
                "local_first_requires_psp": False,
            },
        )

    def test_tenant_policy_cannot_add_runmycampus_transaction_fee(self):
        policy = {"payment_gateways": {"mtn_momo": {"platform_fee": "500.00"}}}
        self.assertEqual(
            get_platform_fee(None, "MTN_MOMO", Decimal("10000.00"), policy=policy),
            Decimal("0"),
        )
