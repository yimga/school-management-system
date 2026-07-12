import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import (
    BillingProcessorSyncEvent,
    PlatformBillingProcessorConfig,
    PlatformLedgerEntry,
    RevenueSharePayout,
    TenantSubscription,
)
from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.billing.services import ensure_subscription_for_school
from apps.observability.models import PlatformIncident
from apps.schools.models import School
from apps.siteconfig.models import Plan


class PlatformBillingWebhookTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Webhook Platform Plan",
            slug="webhook-platform-plan",
            base_price=Decimal("299.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Webhook Billing School",
            slug="webhook-billing-school",
            subdomain="webhook-billing-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.REGULAR,
        )
        ensure_subscription_for_school(self.school)
        self.config = PlatformBillingProcessorConfig.objects.create(
            code="relay",
            display_name="Relay",
            webhook_secret="relay-secret",
            signature_header="X-Signature",
            signature_style=PlatformBillingProcessorConfig.SignatureStyle.PLAIN_HMAC,
            is_active=True,
        )

    def _signature(self, raw_body: bytes) -> str:
        return hmac.new(
            self.config.webhook_secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()

    def _post(self, payload: dict, *, signature: str | None = None):
        raw_body = json.dumps(payload).encode("utf-8")
        sig = signature if signature is not None else self._signature(raw_body)
        return self.client.post(
            "/api/billing/processors/relay/webhook/",
            data=raw_body,
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
            HTTP_X_SIGNATURE=sig,
        )

    def test_relay_webhook_applies_snapshot_and_creates_billing_incident(self):
        response = self._post(
            {
                "school_slug": self.school.slug,
                "event_type": "invoice.payment_failed",
                "account_status": "past_due",
                "subscription_status": "past_due",
                "external_customer_ref": "cus-relay-001",
                "external_subscription_ref": "sub-relay-001",
                "billed_amount": "299.00",
                "currency_code": "USD",
                "current_period_start": (
                    timezone.now() - timedelta(days=10)
                ).isoformat(),
                "current_period_end": (timezone.now() + timedelta(days=20)).isoformat(),
                "message": "Card declined",
            }
        )

        self.assertEqual(response.status_code, 202)
        subscription = TenantSubscription.objects.get(school=self.school)
        self.assertEqual(subscription.status, TenantSubscription.Status.PAST_DUE)
        self.assertEqual(subscription.external_subscription_ref, "sub-relay-001")
        incident = PlatformIncident.objects.get(
            source_system="billing.platform",
            affected_school=self.school,
            incident_type=PlatformIncident.IncidentType.BILLING,
        )
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)
        self.assertEqual(incident.severity, PlatformIncident.Severity.HIGH)

    def test_relay_webhook_rejects_invalid_signature_and_creates_incident(self):
        response = self._post(
            {
                "school_slug": self.school.slug,
                "event_type": "invoice.payment_failed",
                "account_status": "past_due",
                "subscription_status": "past_due",
            },
            signature="deadbeef",
        )

        self.assertEqual(response.status_code, 401)
        failed_event = BillingProcessorSyncEvent.objects.get(
            status=BillingProcessorSyncEvent.Status.FAILED
        )
        self.assertEqual(failed_event.processor_code, "relay")
        self.assertIsNone(failed_event.school)
        incident = PlatformIncident.objects.get(
            source_system="billing.processor_webhook"
        )
        self.assertEqual(
            incident.incident_type, PlatformIncident.IncidentType.INTEGRATION
        )
        self.assertEqual(incident.severity, PlatformIncident.Severity.CRITICAL)

    def test_relay_webhook_rejects_unsupported_content_type(self):
        payload = {
            "school_slug": self.school.slug,
            "event_type": "invoice.payment_failed",
            "account_status": "past_due",
            "subscription_status": "past_due",
        }
        raw_body = json.dumps(payload).encode("utf-8")
        response = self.client.post(
            "/api/billing/processors/relay/webhook/",
            data=raw_body,
            content_type="text/plain",
            HTTP_HOST="manager.runmycampus.com",
            HTTP_X_SIGNATURE=self._signature(raw_body),
        )

        self.assertEqual(response.status_code, 415)
        failed_event = BillingProcessorSyncEvent.objects.get(
            status=BillingProcessorSyncEvent.Status.FAILED
        )
        self.assertEqual(failed_event.processor_code, "relay")
        self.assertIn("Unsupported Content-Type", failed_event.message)

    def test_relay_webhook_resolves_existing_billing_incident_when_account_recovers(
        self,
    ):
        self._post(
            {
                "school_slug": self.school.slug,
                "event_type": "invoice.payment_failed",
                "account_status": "past_due",
                "subscription_status": "past_due",
                "external_customer_ref": "cus-relay-001",
                "external_subscription_ref": "sub-relay-001",
            }
        )

        response = self._post(
            {
                "school_slug": self.school.slug,
                "event_type": "invoice.paid",
                "account_status": "active",
                "subscription_status": "active",
                "external_customer_ref": "cus-relay-001",
                "external_subscription_ref": "sub-relay-001",
            }
        )

        self.assertEqual(response.status_code, 202)
        incident = PlatformIncident.objects.get(
            source_system="billing.platform",
            affected_school=self.school,
            incident_type=PlatformIncident.IncidentType.BILLING,
        )
        self.assertEqual(incident.status, PlatformIncident.Status.RESOLVED)

    def test_relay_webhook_unresolved_school_creates_integration_incident(self):
        response = self._post(
            {
                "school_slug": "missing-school",
                "event_type": "invoice.payment_failed",
                "account_status": "past_due",
                "subscription_status": "past_due",
            }
        )

        self.assertEqual(response.status_code, 422)
        incident = (
            PlatformIncident.objects.filter(source_system="billing.processor_webhook")
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(incident)
        self.assertIn("school resolution failed", incident.title.lower())

    def test_stripe_webhook_accepts_v1_signature_and_applies_snapshot(self):
        stripe_config = PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            webhook_secret="whsec_test_123",
            signature_header="Stripe-Signature",
            signature_style=PlatformBillingProcessorConfig.SignatureStyle.STRIPE_V1,
            is_active=True,
        )
        payload = {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": "in_123",
                    "customer": "cus_stripe_001",
                    "subscription": "sub_stripe_001",
                    "status": "past_due",
                    "currency": "usd",
                    "amount_due": 29900,
                    "current_period_start": int(
                        (timezone.now() - timedelta(days=3)).timestamp()
                    ),
                    "current_period_end": int(
                        (timezone.now() + timedelta(days=27)).timestamp()
                    ),
                    "metadata": {
                        "school_slug": self.school.slug,
                        "school_id": str(self.school.pk),
                    },
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        timestamp = int(timezone.now().timestamp())
        signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
        signature = hmac.new(
            stripe_config.webhook_secret.encode(), signed_payload, hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            "/api/billing/processors/stripe/webhook/",
            data=raw_body,
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
            HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={signature}",
        )

        self.assertEqual(response.status_code, 202)
        subscription = TenantSubscription.objects.get(school=self.school)
        self.assertEqual(subscription.status, TenantSubscription.Status.PAST_DUE)
        self.assertEqual(subscription.external_subscription_ref, "sub_stripe_001")

    def test_stripe_webhook_invoice_paid_creates_ledger_when_amount_positive(self):
        stripe_config = PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            webhook_secret="whsec_test_456",
            signature_header="Stripe-Signature",
            signature_style=PlatformBillingProcessorConfig.SignatureStyle.STRIPE_V1,
            is_active=True,
        )
        payload = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_paid_1",
                    "customer": "cus_stripe_paid",
                    "subscription": "sub_stripe_paid",
                    "status": "paid",
                    "currency": "usd",
                    "amount_paid": 19900,
                    "current_period_start": int(
                        (timezone.now() - timedelta(days=2)).timestamp()
                    ),
                    "current_period_end": int(
                        (timezone.now() + timedelta(days=28)).timestamp()
                    ),
                    "metadata": {
                        "school_slug": self.school.slug,
                    },
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        timestamp = int(timezone.now().timestamp())
        signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
        signature = hmac.new(
            stripe_config.webhook_secret.encode(), signed_payload, hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            "/api/billing/processors/stripe/webhook/",
            data=raw_body,
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
            HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={signature}",
        )

        self.assertEqual(response.status_code, 202)
        self.assertTrue(
            PlatformLedgerEntry.objects.filter(
                source="stripe_webhook",
                reference__contains="stripe:invoice.paid:",
            ).exists()
        )

    def test_stripe_webhook_invoice_paid_posts_credit_that_settles_renewal(self):
        """invoice.paid is a SETTLEMENT of the internal renewal charge, so it must
        post a CREDIT that brings the balance back down — not a second CHARGE that
        ages a paying tenant into PAST_DUE/SUSPENDED (the pre-fix behaviour)."""
        from apps.billing.services import (
            platform_account_balance,
            record_platform_charge,
        )

        account, _sub, _ = ensure_subscription_for_school(self.school)
        baseline = platform_account_balance(account)
        # The billing-lifecycle sweep posts this renewal CHARGE for every tenant
        # (PSP tenants included). It is exactly what the Stripe payment settles.
        record_platform_charge(
            school=self.school,
            amount=Decimal("199.00"),
            description="Platform subscription renewal (test)",
            reference="test-renewal-charge-199",
            source="billing_lifecycle",
        )
        self.assertEqual(
            platform_account_balance(account), baseline + Decimal("199.00")
        )

        stripe_config = PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            webhook_secret="whsec_settle_1",
            signature_header="Stripe-Signature",
            signature_style=PlatformBillingProcessorConfig.SignatureStyle.STRIPE_V1,
            is_active=True,
        )
        payload = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_settle_1",
                    "customer": "cus_settle",
                    "subscription": "sub_settle",
                    "status": "paid",
                    "currency": "usd",
                    "amount_paid": 19900,
                    "current_period_start": int(
                        (timezone.now() - timedelta(days=2)).timestamp()
                    ),
                    "current_period_end": int(
                        (timezone.now() + timedelta(days=28)).timestamp()
                    ),
                    "metadata": {"school_slug": self.school.slug},
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        timestamp = int(timezone.now().timestamp())
        signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
        signature = hmac.new(
            stripe_config.webhook_secret.encode(), signed_payload, hashlib.sha256
        ).hexdigest()
        response = self.client.post(
            "/api/billing/processors/stripe/webhook/",
            data=raw_body,
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
            HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={signature}",
        )
        self.assertEqual(response.status_code, 202)

        entry = PlatformLedgerEntry.objects.get(
            source="stripe_webhook",
            reference__contains="stripe:invoice.paid:",
        )
        self.assertEqual(entry.entry_type, PlatformLedgerEntry.EntryType.CREDIT)
        self.assertEqual(entry.amount, Decimal("199.00"))
        # Payment settles the renewal charge → balance returns to baseline, NOT
        # baseline + 2x (the pre-fix double-debit that suspended paying tenants).
        self.assertEqual(platform_account_balance(account), baseline)

    def test_checkout_session_completed_stays_charge_not_credit(self):
        """checkout.session.completed is intentionally NOT flipped to CREDIT: it also
        carries marketplace add-on purchases with no matching internal charge to
        settle. Only invoice.* settlements become credits — this locks that
        boundary so a future 'flip them all' change can't silently regress it."""
        response = self._post(
            {
                "school_slug": self.school.slug,
                "school_id": str(self.school.pk),
                "event_type": "checkout.session.completed",
                "processor_source_ref": "cs_charge_guard_1",
                "billed_amount": "40.00",
                "currency_code": "USD",
                "account_status": "active",
                "subscription_status": "active",
                "external_customer_ref": "cus-guard-1",
                "external_subscription_ref": "sub-guard-1",
            }
        )
        self.assertEqual(response.status_code, 202)
        entry = PlatformLedgerEntry.objects.get(
            source="stripe_webhook",
            reference__contains="relay:checkout.session.completed:",
        )
        self.assertEqual(entry.entry_type, PlatformLedgerEntry.EntryType.CHARGE)

    def test_relay_webhook_checkout_completed_applies_marketplace_addon(self):
        pub = PublisherOrganization.objects.create(
            slug="mkt-pub-web",
            name="Mkt Pub",
        )
        app = MarketplaceApp.objects.create(
            slug="mkt-webhook-app",
            name="Webhook App",
            version="1.0.0",
            manifest={
                "pricing_type": "paid",
                "billing_sku": "sku_wh_app",
                "required_features": ["reports"],
            },
            publisher=pub,
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
        )
        MarketplaceListing.objects.create(
            app=app,
            publisher=pub,
            status=MarketplaceListing.Status.APPROVED,
            revenue_share_percent=Decimal("15.00"),
            short_description="x",
        )

        response = self._post(
            {
                "school_slug": self.school.slug,
                "school_id": str(self.school.pk),
                "event_type": "checkout.session.completed",
                "marketplace_app_id": str(app.pk),
                "processor_source_ref": "cs_test_sess_1",
                "billed_amount": "40.00",
                "currency_code": "USD",
                "account_status": "active",
                "subscription_status": "active",
                "external_customer_ref": "cus-mkt-1",
                "external_subscription_ref": "sub-mkt-1",
            }
        )

        self.assertEqual(response.status_code, 202)
        self.school.refresh_from_db()
        addons = list(self.school.addons or [])
        self.assertIn("sku_wh_app", addons)
        self.assertIn("reports", addons)
        payouts = RevenueSharePayout.objects.filter(
            source_school=self.school,
            processor_code="relay",
        ).order_by("-pk")[:10]
        payout = None
        for p in payouts:
            md = p.metadata if isinstance(p.metadata, dict) else {}
            if md.get("marketplace_addon_session_ref") == "cs_test_sess_1":
                payout = p
                break
        self.assertIsNotNone(payout)
        self.assertEqual(payout.status, RevenueSharePayout.Status.DRAFT)

    def test_unknown_processor_webhook_returns_404(self):
        response = self.client.post(
            "/api/billing/processors/not-a-processor/webhook/",
            data=b"{}",
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 404)
