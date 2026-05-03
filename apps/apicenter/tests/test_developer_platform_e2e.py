"""
End-to-end developer platform chain (OAuth + tenant install + scoped API + webhook HTTP).

Proves: DeveloperApplication (registration parity path) → OAuth token → active
AppInstallation on tenant host → scope-enforced GET /api/v1/platform/scoped-ping/ →
tenant webhook subscription → enqueue_webhook_event → deliver_webhook_delivery (HTTP POST)
with verified HMAC signature → marketplace webhook audit hook.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.apicenter.models import DeveloperApplication, _hash_secret
from apps.events.models import WebhookDelivery, WebhookSubscription
from apps.events.webhooks import deliver_webhook_delivery, enqueue_webhook_event, sign_payload
from apps.marketplace.lifecycle import emit_webhook_audit, install_app
from apps.marketplace.models import (
    AppAuditLog,
    AppInstallation,
    AppScope,
    MarketplaceApp,
    PublisherOrganization,
    TenantMarketplaceSubscription,
)
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class DeveloperPlatformE2ETests(TestCase):
    """Extends the same host/school pattern as ``DeveloperPlatformTests``."""

    def setUp(self):
        self.school = School.objects.create(
            name="E2E Dev School",
            slug="e2e-dev-school",
            subdomain="e2e-dev-school",
            is_active=True,
        )
        pub, _ = PublisherOrganization.objects.get_or_create(
            slug="pub-e2e",
            defaults={
                "name": "E2E Pub",
                "verification_status": PublisherOrganization.VerificationStatus.VERIFIED,
            },
        )
        self.market_app = MarketplaceApp.objects.create(
            publisher=pub,
            slug="e2e-oauth-app",
            name="E2E OAuth App",
            version="1.0.0",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            is_intentionally_free=True,
        )
        AppScope.objects.create(
            app=self.market_app, scope_code="ping:read", description="ping"
        )
        raw_secret = "cs_e2e_secret_only_for_tests_xxxxx"
        self.dev_app = DeveloperApplication.objects.create(
            name="E2E OAuth Client",
            app_key="rmcapp_e2eoauth123456",
            client_id="rmc_e2e_client_id_xxxxxxxx",
            client_secret_hash=_hash_secret(raw_secret),
            redirect_uris=["http://127.0.0.1:9999/callback"],
            scopes=["read"],
            marketplace_app=self.market_app,
            is_active=True,
        )
        self.raw_client_secret = raw_secret

    def _host(self):
        return {"HTTP_HOST": f"{self.school.subdomain}.runmycampus.com"}

    def test_oauth_install_scoped_api_webhook_audit_chain(self):
        client = Client()

        # 1) OAuth client_credentials
        tok = client.post(
            "/api/v1/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.dev_app.client_id,
                    "client_secret": self.raw_client_secret,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(tok.status_code, 200, tok.content)
        access = tok.json()["access_token"]
        self.assertTrue(access.startswith("rmc_at_"))

        # 2) Tenant installs app (grants ping:read)
        inst = install_app(
            school=self.school,
            app=self.market_app,
            grant_scope_codes=["ping:read"],
        )
        self.assertEqual(inst.status, AppInstallation.Status.ACTIVE)

        tms = TenantMarketplaceSubscription.objects.filter(installation=inst).first()
        self.assertIsNotNone(tms)
        self.assertEqual(tms.status, TenantMarketplaceSubscription.Status.ACTIVE)

        # 3) Webhook subscription row (domain events delivery surface)
        wh = WebhookSubscription.objects.create(
            school_id=self.school.id,
            url="https://hooks.example/e2e",
            event_types=["student.created"],
            secret="whsec_test",
            is_active=True,
        )
        self.assertTrue(wh.pk)

        # 4) Domain event → queued delivery → HTTP POST receive (injectable transport)
        captured: list[bytes] = []

        def fake_http_post(url, body, headers, timeout):
            self.assertEqual(url, wh.url)
            captured.append(body)
            expected_sig = sign_payload(wh.secret or "", body)
            self.assertEqual(headers.get("X-Webhook-Signature"), expected_sig)
            self.assertEqual(headers.get("X-Webhook-Event"), "student.created")
            return 200, "ok"

        deliveries = enqueue_webhook_event(
            school=self.school,
            event_type="student.created",
            data={"install_id": str(inst.id), "proof": "ci_e2e"},
        )
        self.assertEqual(len(deliveries), 1)
        result = deliver_webhook_delivery(
            deliveries[0], http_post=fake_http_post, now=None
        )
        self.assertEqual(result["status"], WebhookDelivery.Status.DELIVERED)
        deliveries[0].refresh_from_db()
        self.assertEqual(deliveries[0].status, WebhookDelivery.Status.DELIVERED)

        envelope = json.loads(captured[0])
        self.assertEqual(envelope.get("event_type"), "student.created")
        self.assertEqual(
            (envelope.get("data") or {}).get("proof"),
            "ci_e2e",
        )

        # 5) Marketplace install webhook audit trail (secondary pathway)
        emit_webhook_audit(inst, "e2e.proof", {"install_id": str(inst.id)})
        audit = AppAuditLog.objects.filter(
            action="marketplace.webhook.e2e.proof"
        ).first()
        self.assertIsNotNone(audit)

        # 6) OAuth Bearer on tenant host: integration context
        ctx_url = reverse("api_v1:platform-integration-context")
        r_ctx = client.get(
            ctx_url,
            HTTP_AUTHORIZATION=f"Bearer {access}",
            **self._host(),
        )
        self.assertEqual(r_ctx.status_code, 200, r_ctx.content)
        ctx = r_ctx.json()
        self.assertTrue(ctx.get("app_auth"))
        self.assertEqual(ctx.get("app_auth_mode"), "oauth_access_token")
        self.assertEqual(ctx.get("marketplace_installation_id"), str(inst.id))
        self.assertIn("ping:read", ctx.get("app_scope") or [])

        # 7) Scope-enforced ping succeeds
        ping_url = reverse("api_v1:platform-scoped-ping")
        r_ok = client.get(
            ping_url,
            HTTP_AUTHORIZATION=f"Bearer {access}",
            **self._host(),
        )
        self.assertEqual(r_ok.status_code, 200, r_ok.content)
        self.assertTrue(r_ok.json().get("ok"))

        # 8) Same token on wrong tenant host → no installation resolution
        other = School.objects.create(
            name="Other E2E",
            slug="other-e2e",
            subdomain="other-e2e",
            is_active=True,
        )
        r_bad = client.get(
            ping_url,
            HTTP_AUTHORIZATION=f"Bearer {access}",
            HTTP_HOST=f"{other.subdomain}.runmycampus.com",
        )
        self.assertEqual(r_bad.status_code, 401)

    def test_oauth_ping_forbidden_without_ping_scope_grant(self):
        """Installation without ping:read grant → 403 even with valid OAuth token."""
        client = Client()
        tok = client.post(
            "/api/v1/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.dev_app.client_id,
                    "client_secret": self.raw_client_secret,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        access = tok.json()["access_token"]
        install_app(school=self.school, app=self.market_app, grant_scope_codes=[])
        ping_url = reverse("api_v1:platform-scoped-ping")
        r = client.get(
            ping_url,
            HTTP_AUTHORIZATION=f"Bearer {access}",
            **self._host(),
        )
        self.assertEqual(r.status_code, 403)


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class DeveloperPlatformMonetizationGateTests(TestCase):
    """Paid install gate when MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING is on."""

    def setUp(self):
        from decimal import Decimal

        self.school = School.objects.create(
            name="Pay Gate School",
            slug="pay-gate-school",
            subdomain="pay-gate-school",
            is_active=True,
        )
        pub, _ = PublisherOrganization.objects.get_or_create(
            slug="pub-paygate",
            defaults={
                "name": "PayGate Pub",
                "verification_status": PublisherOrganization.VerificationStatus.VERIFIED,
            },
        )
        self.paid_app = MarketplaceApp.objects.create(
            publisher=pub,
            slug="paid-sub-app",
            name="Paid Sub App",
            version="1.0.0",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
            price=Decimal("9.99"),
            billing_interval=MarketplaceApp.BillingInterval.MONTHLY,
        )

    def test_paid_install_raises_when_billing_gate_enabled_without_customer(self):
        from apps.marketplace.services import ensure_marketplace_listing, install_app

        ensure_marketplace_listing(self.paid_app)
        with override_settings(MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING=True):
            with self.assertRaises(RuntimeError) as ctx:
                install_app(school=self.school, app=self.paid_app)
        self.assertIn("Paid marketplace install blocked", str(ctx.exception))
