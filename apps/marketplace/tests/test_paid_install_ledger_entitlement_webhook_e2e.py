"""GEOS-99: paid install → subscription → ledger → webhook replay E2E."""

from __future__ import annotations

import uuid

from django.test import override_settings

from apps.billing.models import BillingAccount
from apps.billing.services import ensure_billing_account_for_school
from apps.finance.webhooks.claim import claim_webhook_processing
from apps.marketplace.models import (
    MarketplaceMonetizationLedgerEntry,
    TenantMarketplaceSubscription,
)
from apps.marketplace.services import install_app, uninstall_app
from apps.marketplace.tests.test_marketplace_monetization_closure import (
    MarketplaceMonetizationClosureTests,
)


@override_settings(MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING=True)
class PaidInstallLedgerEntitlementWebhookE2ETests(MarketplaceMonetizationClosureTests):
    """Single chain: install → subscription + ledger → uninstall ledger → webhook claim idempotency."""

    def test_paid_install_ledger_entitlement_webhook_replay_chain(self):
        ensure_billing_account_for_school(self.school)
        acct = BillingAccount.objects.get(school=self.school)
        acct.external_customer_ref = "cus_geos_e2e"
        acct.save(update_fields=["external_customer_ref"])

        install_app(self.school, self.paid_app, actor=None)
        sub = TenantMarketplaceSubscription.objects.get(school=self.school, app=self.paid_app)
        self.assertTrue(sub.is_active)
        ledger_install = MarketplaceMonetizationLedgerEntry.objects.filter(
            school=self.school,
            app=self.paid_app,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.INSTALL,
        )
        self.assertEqual(ledger_install.count(), 1)

        uninstall_app(self.school, self.paid_app, actor=None)
        ledger_uninstall = MarketplaceMonetizationLedgerEntry.objects.filter(
            school=self.school,
            app=self.paid_app,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.UNINSTALL,
        )
        self.assertGreaterEqual(ledger_uninstall.count(), 1)

        dedupe_key = f"geos-e2e-{uuid.uuid4().hex}"
        r1, _ = claim_webhook_processing(
            provider="stripe",
            bucket=dedupe_key,
            reference_id=dedupe_key,
            client_ip="127.0.0.1",
        )
        r2, _ = claim_webhook_processing(
            provider="stripe",
            bucket=dedupe_key,
            reference_id=dedupe_key,
            client_ip="127.0.0.1",
        )
        self.assertEqual(r1, "claimed")
        self.assertEqual(r2, "duplicate")
