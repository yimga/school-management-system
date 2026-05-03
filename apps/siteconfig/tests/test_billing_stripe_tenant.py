"""Tenant Stripe checkout / portal routes (guarded; mocked Stripe HTTP)."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.billing.models import PlatformBillingProcessorConfig, StripePlanPrice
from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.marketplace.manifest_schema import normalize_platform_manifest
from apps.billing.services import ensure_subscription_for_school
from apps.people.models import TeacherProfile
from apps.siteconfig.models import Plan
from apps.schools.models import School, SchoolMembership

_T_HOST = "stripetenant.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class BillingStripeTenantRoutesTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Pro Stripe",
            slug="pro",
            base_price=Decimal("99.00"),
            is_active=True,
        )
        cls.school = School.objects.create(
            name="Stripe Tenant School",
            slug="stripetenant",
            subdomain="stripetenant",
            is_active=True,
            plan=cls.plan,
        )
        ensure_subscription_for_school(cls.school)
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        StripePlanPrice.objects.create(
            plan_code="pro",
            stripe_price_id="price_test_001",
            billing_cycle=StripePlanPrice.BillingCycle.MONTHLY,
            currency="USD",
            is_active=True,
        )

    def _staff_with_perm(self) -> User:
        u = User.objects.create_user(
            username=f"st_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            email="op@example.com",
        )
        u.feature_permissions.add(self.perm_settings)
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="S1")
        SchoolMembership.objects.get_or_create(
            user=u,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        return u

    def test_checkout_redirects_when_processor_missing(self):
        u = self._staff_with_perm()
        c = Client(HTTP_HOST=_T_HOST)
        self.assertTrue(c.login(username=u.username, password="x" * 8))
        url = reverse("siteconfig:billing_checkout_start", urlconf="config.tenant_urls")
        resp = c.get(f"{url}?plan_code=pro", follow=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace").lower()
        self.assertTrue("not configured" in body or "billing processor" in body)

    def test_checkout_redirects_to_stripe_when_configured(self):
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={"secret_key": "sk_test_xxx"},
        )
        u = self._staff_with_perm()
        c = Client(HTTP_HOST=_T_HOST)
        self.assertTrue(c.login(username=u.username, password="x" * 8))
        url = reverse("siteconfig:billing_checkout_start", urlconf="config.tenant_urls")

        def fake_post(target_url, payload, headers, timeout):
            return (
                200,
                {"url": "https://checkout.stripe.com/session/test"},
                json.dumps({"url": "https://checkout.stripe.com/session/test"}),
            )

        with patch(
            "apps.billing.stripe_checkout._default_form_post", side_effect=fake_post
        ):
            resp = c.get(f"{url}?plan_code=pro")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "https://checkout.stripe.com/session/test")

    def test_portal_blocked_without_customer_ref(self):
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={"secret_key": "sk_test_xxx"},
        )
        u = self._staff_with_perm()
        c = Client(HTTP_HOST=_T_HOST)
        self.assertTrue(c.login(username=u.username, password="x" * 8))
        url = reverse("siteconfig:billing_customer_portal", urlconf="config.tenant_urls")
        resp = c.get(url, follow=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace").lower()
        self.assertTrue("not linked" in body or "stripe customer" in body)

    def test_portal_redirects_when_customer_linked(self):
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={"secret_key": "sk_test_xxx"},
        )
        account, _sub, _ = ensure_subscription_for_school(self.school)
        account.external_customer_ref = "cus_test_123"
        account.save(update_fields=["external_customer_ref", "updated_at"])
        u = self._staff_with_perm()
        c = Client(HTTP_HOST=_T_HOST)
        self.assertTrue(c.login(username=u.username, password="x" * 8))
        url = reverse("siteconfig:billing_customer_portal", urlconf="config.tenant_urls")

        def fake_post(target_url, payload, headers, timeout):
            return (
                200,
                {"url": "https://billing.stripe.com/session/test_portal"},
                "{}",
            )

        with patch(
            "apps.billing.stripe_checkout._default_form_post", side_effect=fake_post
        ):
            resp = c.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "https://billing.stripe.com/session/test_portal")

    def test_marketplace_checkout_uses_billing_sku_price(self):
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={"secret_key": "sk_test_xxx"},
        )
        pub = PublisherOrganization.objects.create(
            slug="sku-pub", name="SKU Pub", verification_status="verified"
        )
        app = MarketplaceApp.objects.create(
            slug="sku-app",
            name="SKU App",
            version="1.0.0",
            manifest={
                "pricing_type": "paid",
                "billing_sku": "mkt_addon_sku_1",
            },
            publisher=pub,
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
        )
        MarketplaceListing.objects.create(
            app=app,
            publisher=pub,
            status=MarketplaceListing.Status.APPROVED,
            short_description="x",
        )
        normalize_platform_manifest(
            dict(app.manifest or {}),
            app_slug=app.slug,
            app_name=app.name,
            version=app.version or "",
            publisher_slug=pub.slug,
        )
        StripePlanPrice.objects.create(
            plan_code="mkt_addon_sku_1",
            stripe_price_id="price_mkt_addon_1",
            billing_cycle=StripePlanPrice.BillingCycle.MONTHLY,
            currency="USD",
            is_active=True,
        )
        u = self._staff_with_perm()
        c = Client(HTTP_HOST=_T_HOST)
        self.assertTrue(c.login(username=u.username, password="x" * 8))
        url = reverse("siteconfig:billing_checkout_start", urlconf="config.tenant_urls")

        def fake_post(target_url, payload, headers, timeout):
            self.assertEqual(
                payload.get("line_items[0][price]"), "price_mkt_addon_1"
            )
            self.assertEqual(
                str(payload.get("metadata[billing_context]")),
                "marketplace_addon",
            )
            return (
                200,
                {"url": "https://checkout.stripe.com/session/mkt_test"},
                '{"url":"https://checkout.stripe.com/session/mkt_test"}',
            )

        with patch(
            "apps.billing.stripe_checkout._default_form_post", side_effect=fake_post
        ):
            resp = c.get(f"{url}?marketplace_app_id={app.pk}")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "https://checkout.stripe.com/session/mkt_test")

    def test_marketplace_checkout_blocked_when_kill_switch_active(self):
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={"secret_key": "sk_test_xxx"},
        )
        pub = PublisherOrganization.objects.create(
            slug="ks-pub", name="KS Pub", verification_status="verified"
        )
        app = MarketplaceApp.objects.create(
            slug="ks-app",
            name="KS App",
            version="1.0.0",
            manifest={"pricing_type": "paid", "billing_sku": "mkt_ks_sku"},
            publisher=pub,
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
        )
        MarketplaceListing.objects.create(
            app=app,
            publisher=pub,
            status=MarketplaceListing.Status.APPROVED,
            short_description="x",
            kill_switch_active=True,
        )
        StripePlanPrice.objects.create(
            plan_code="mkt_ks_sku",
            stripe_price_id="price_ks_1",
            billing_cycle=StripePlanPrice.BillingCycle.MONTHLY,
            currency="USD",
            is_active=True,
        )
        u = self._staff_with_perm()
        c = Client(HTTP_HOST=_T_HOST)
        self.assertTrue(c.login(username=u.username, password="x" * 8))
        url = reverse("siteconfig:billing_checkout_start", urlconf="config.tenant_urls")
        resp = c.get(f"{url}?marketplace_app_id={app.pk}", follow=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace").lower()
        self.assertTrue(
            "unavailable" in body or "temporarily" in body or "kill" in body
        )

    def test_unauthorized_user_redirected_from_checkout(self):
        u = User.objects.create_user(
            username="no_perm_stripe",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="T9")
        c = Client(HTTP_HOST=_T_HOST)
        self.assertTrue(c.login(username="no_perm_stripe", password="x" * 8))
        url = reverse("siteconfig:billing_checkout_start", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertIn(resp.status_code, (302, 403))
