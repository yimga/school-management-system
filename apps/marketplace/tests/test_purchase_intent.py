"""marketplace:app_purchase_intent routing (no fake purchase completion)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.billing.models import PlatformBillingProcessorConfig, StripePlanPrice
from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.people.models import TeacherProfile
from apps.siteconfig.models import Plan
from apps.schools.models import School, SchoolMembership

_T_HOST = "purch.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class AppPurchaseIntentTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Growth", slug="growth", is_active=True)
        cls.school = School.objects.create(
            name="Purchase School",
            slug="purch",
            subdomain="purch",
            is_active=True,
            plan=cls.plan,
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="pi-pub",
            name="PI Pub",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )
        cls.perm_manage, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def _login_manager(self):
        u = User.objects.create_user(
            username=f"mkt_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="PI1")
        SchoolMembership.objects.get_or_create(
            user=u,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        u.feature_permissions.add(self.perm_manage)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        return c

    def test_free_app_redirects_to_catalog(self):
        app = MarketplaceApp.objects.create(
            slug="free-app",
            name="Free App",
            version="1.0.0",
            manifest={"pricing_type": "free"},
            publisher=self.publisher,
            is_intentionally_free=True,
        )
        MarketplaceListing.objects.create(
            app=app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            short_description="x",
        )
        c = self._login_manager()
        url = reverse(
            "marketplace:app_purchase_intent",
            kwargs={"app_id": app.pk},
            urlconf="config.tenant_urls",
        )
        resp = c.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("focus_app=", resp["Location"])

    def test_paid_app_redirects_to_checkout_when_stripe_ready(self):
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={"secret_key": "sk_test_x"},
        )
        StripePlanPrice.objects.get_or_create(
            plan_code="addon_paid_app",
            billing_cycle=StripePlanPrice.BillingCycle.MONTHLY,
            currency="USD",
            defaults={
                "stripe_price_id": "price_mkt_test_1",
                "is_active": True,
            },
        )
        app = MarketplaceApp.objects.create(
            slug="paid-app",
            name="Paid App",
            version="1.0.0",
            manifest={
                "pricing_type": "paid",
                "price_display": "$5",
                "billing_sku": "addon_paid_app",
            },
            publisher=self.publisher,
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
        )
        MarketplaceListing.objects.create(
            app=app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            revenue_share_percent=Decimal("10.00"),
            short_description="x",
        )
        c = self._login_manager()
        url = reverse(
            "marketplace:app_purchase_intent",
            kwargs={"app_id": app.pk},
            urlconf="config.tenant_urls",
        )
        resp = c.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/siteconfig/billing/checkout/start/", resp["Location"])
        self.assertIn("marketplace_app_id=", resp["Location"])
        self.assertNotIn("success=1", resp["Location"].lower())

    def test_paid_app_falls_back_to_plan_when_stripe_missing(self):
        app = MarketplaceApp.objects.create(
            slug="paid-app-2",
            name="Paid App 2",
            version="1.0.0",
            manifest={"pricing_type": "paid", "billing_sku": "addon_x"},
            publisher=self.publisher,
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
        )
        MarketplaceListing.objects.create(
            app=app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            short_description="x",
        )
        c = self._login_manager()
        url = reverse(
            "marketplace:app_purchase_intent",
            kwargs={"app_id": app.pk},
            urlconf="config.tenant_urls",
        )
        resp = c.get(url, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/siteconfig/billing/plan/", resp["Location"])
