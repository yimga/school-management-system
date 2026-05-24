"""End-state marketplace monetization closure checks (tenant UX + install/uninstall ledger)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission, User
from apps.billing.models import BillingAccount
from apps.billing.services import ensure_billing_account_for_school
from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceMonetizationLedgerEntry,
    PublisherOrganization,
    TenantMarketplaceSubscription,
)
from apps.marketplace.services import install_app, uninstall_app
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership

_T_HOST = "mclose.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST],
    MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING=True,
)
class MarketplaceMonetizationClosureTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="MClose School",
            slug="mclose",
            subdomain="mclose",
            is_active=True,
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="mclose-pub",
            name="MClose Pub",
        )
        cls.paid_app = MarketplaceApp.objects.create(
            slug="mclose-paid",
            app_key="mclose-paid",
            name="MClose Paid",
            version="1.0.0",
            publisher=cls.publisher,
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
            price=Decimal("55.00"),
            billing_interval=MarketplaceApp.BillingInterval.MONTHLY,
        )
        MarketplaceListing.objects.create(
            app=cls.paid_app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            revenue_share_percent=Decimal("60.00"),
            short_description="x",
        )
        cls.free_app = MarketplaceApp.objects.create(
            slug="mclose-free",
            app_key="mclose-free",
            name="MClose Free",
            version="1.0.0",
            publisher=cls.publisher,
            pricing_model=MarketplaceApp.PricingModel.FREE,
            is_intentionally_free=True,
            manifest={"x": 1},
        )
        MarketplaceListing.objects.create(
            app=cls.free_app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            revenue_share_percent=Decimal("0.00"),
            short_description="y",
        )
        cls.perm_manage, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def _login_admin(self):
        u = User.objects.create_user(
            username=f"mclose_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="MC1")
        SchoolMembership.objects.get_or_create(
            user=u,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        u.feature_permissions.add(self.perm_manage)
        TOTPDevice.objects.create(user=u, name="test-device", confirmed=True)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        session = c.session
        session["mfa_verified"] = True
        session.save()
        return c

    def _login_teacher(self):
        u = User.objects.create_user(
            username=f"tchr_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.TEACHER,
            is_staff=False,
        )
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="T1")
        SchoolMembership.objects.get_or_create(
            user=u,
            school=self.school,
            defaults={"role": User.Role.TEACHER, "is_primary": True},
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        return c

    def test_paid_install_creates_subscription_and_ledger_slice(self):
        ensure_billing_account_for_school(self.school)
        acct = BillingAccount.objects.get(school=self.school)
        acct.external_customer_ref = "cus_close_1"
        acct.save(update_fields=["external_customer_ref", "updated_at"])
        inst = install_app(self.school, self.paid_app, skip_compatibility=True)
        sub = TenantMarketplaceSubscription.objects.filter(installation=inst).first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.status, TenantMarketplaceSubscription.Status.ACTIVE)
        led = MarketplaceMonetizationLedgerEntry.objects.filter(
            school=self.school,
            installation=inst,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.INSTALL,
        )
        self.assertTrue(led.exists())

    def test_uninstall_disables_subscription_and_adds_uninstall_ledger(self):
        ensure_billing_account_for_school(self.school)
        acct = BillingAccount.objects.get(school=self.school)
        acct.external_customer_ref = "cus_close_2"
        acct.save(update_fields=["external_customer_ref", "updated_at"])
        inst = install_app(self.school, self.paid_app, skip_compatibility=True)
        uninstall_app(self.school, self.paid_app)
        sub = TenantMarketplaceSubscription.objects.get(installation=inst)
        self.assertEqual(sub.status, TenantMarketplaceSubscription.Status.CANCELED)
        self.assertTrue(
            MarketplaceMonetizationLedgerEntry.objects.filter(
                school=self.school,
                installation=inst,
                event_type=MarketplaceMonetizationLedgerEntry.EventType.UNINSTALL,
            ).exists()
        )

    def test_monetization_dashboard_not_exposed_on_tenant_marketplace_urlconf(self):
        with self.assertRaises(NoReverseMatch):
            reverse(
                "marketplace:monetization_dashboard",
                urlconf="config.tenant_urls",
            )

    def test_tenant_marketplace_purchase_intent_route_still_resolves(self):
        url = reverse(
            "marketplace:app_purchase_intent",
            kwargs={"app_id": self.free_app.pk},
            urlconf="config.tenant_urls",
        )
        self.assertEqual(url, f"/marketplace/app/{self.free_app.pk}/purchase-intent/")
