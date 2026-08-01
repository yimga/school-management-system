from decimal import Decimal
from pathlib import Path

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

    def test_embedded_checkout_never_reads_operator_billing_credentials(self):
        root = Path(__file__).resolve().parents[3]
        creators = (root / "apps/billing/embedded_checkout_psp_creators.py").read_text(
            encoding="utf-8"
        )
        stripe = (root / "apps/billing/embedded_checkout_stripe_dynamic.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("PlatformBillingProcessorConfig", creators)
        self.assertNotIn("get_active_stripe_processor_config", stripe)
        self.assertIn('_tenant_psp_config("stripe", req.tenant_id)', stripe)

    def test_stripe_connect_checklist_requires_direct_tenant_settlement(self):
        root = Path(__file__).resolve().parents[3]
        checklist = (root / "apps/finance/payment_lane2_checklist.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Direct charge on connected account with tenant payout proof", checklist)
        self.assertIn("no destination charge or application fee", checklist)
