"""SFDP 1426 — finance write 402 when billing inactive."""

from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.billing.models import BillingAccount
from apps.finance.models import TenantPaymentPolicy
from apps.finance.payment_region_catalog import ensure_canonical_region_payment_profiles
from apps.finance.subscription_gate import (
    FinanceSubscriptionGateMiddleware,
    billing_allows_finance_writes,
)
from apps.schools.models import School


class FinanceSubscriptionGateTests(TestCase):
    def setUp(self):
        ensure_canonical_region_payment_profiles()
        self.school = School.objects.create(
            name="Gate School",
            slug="gate-school-sfdp",
            subdomain="gate-school-sfdp",
            country_code="NG",
            is_active=True,
        )
        from apps.finance.models import RegionPaymentProfile

        rp = RegionPaymentProfile.objects.get(country_code="NG")
        TenantPaymentPolicy.objects.create(
            school=self.school,
            region_profile=rp,
            allow_manual_offline_proof=True,
        )

    def test_active_billing_allows_writes(self):
        BillingAccount.objects.create(
            school=self.school,
            status=BillingAccount.Status.ACTIVE,
        )
        self.assertTrue(billing_allows_finance_writes(self.school))

    def test_suspended_billing_blocks_writes(self):
        BillingAccount.objects.create(
            school=self.school,
            status=BillingAccount.Status.SUSPENDED,
        )
        self.assertFalse(billing_allows_finance_writes(self.school))

    def test_middleware_returns_402_on_finance_post(self):
        BillingAccount.objects.create(
            school=self.school,
            status=BillingAccount.Status.CANCELED,
        )
        factory = RequestFactory()
        request = factory.post("/finance/fees/generate/")
        request.school = self.school
        response = FinanceSubscriptionGateMiddleware(lambda r: None).process_request(request)
        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response.status_code, 402)

    def test_marketplace_path_exempt_when_billing_inactive(self):
        BillingAccount.objects.create(
            school=self.school,
            status=BillingAccount.Status.SUSPENDED,
        )
        factory = RequestFactory()
        request = factory.post("/marketplace/addons/install/")
        request.school = self.school
        response = FinanceSubscriptionGateMiddleware(lambda r: None).process_request(request)
        self.assertIsNone(response)

    def test_upload_receipt_exempt_when_offline_proof_allowed(self):
        BillingAccount.objects.create(
            school=self.school,
            status=BillingAccount.Status.SUSPENDED,
        )
        factory = RequestFactory()
        request = factory.post("/finance/invoices/1/upload-receipt/")
        request.school = self.school
        response = FinanceSubscriptionGateMiddleware(lambda r: None).process_request(request)
        self.assertIsNone(response)
