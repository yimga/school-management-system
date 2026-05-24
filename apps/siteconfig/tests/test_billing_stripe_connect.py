"""Tenant Stripe Connect onboarding routes (mocked Stripe HTTP)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.billing.models import PlatformBillingProcessorConfig
from apps.people.models import TeacherProfile
from apps.siteconfig.models import Plan
from apps.schools.models import School, SchoolMembership


_T_HOST = "stripeconnect.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class BillingStripeConnectRoutesTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Connect Plan",
            slug="connect-plan",
            base_price=Decimal("50.00"),
            is_active=True,
        )
        cls.school = School.objects.create(
            name="Connect Tenant School",
            slug="stripeconnect",
            subdomain="stripeconnect",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={
                "secret_key": "sk_test_connect",
                "connect_enabled": True,
                "connect_account_type": "express",
            },
        )

    def _staff_with_perm(self) -> User:
        u = User.objects.create_user(
            username=f"sc_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            email="sc@example.com",
        )
        u.feature_permissions.add(self.perm_settings)
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="SC1")
        SchoolMembership.objects.get_or_create(
            user=u,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        return u

    def test_connect_page_renders(self):
        u = self._staff_with_perm()
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:billing_stripe_connect")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Stripe Connect")

    def test_connect_start_redirects_to_stripe_link(self):
        u = self._staff_with_perm()
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)

        def fake_post(url, data, headers, timeout):
            if url.endswith("/v1/accounts"):
                return 200, {"id": "acct_new", "type": "express"}, "{}"
            if url.endswith("/v1/account_links"):
                return 200, {"url": "https://connect.stripe.com/setup/test"}, "{}"
            return 400, {}, "bad"

        with patch(
            "apps.billing.stripe_connect_onboarding._default_form_post",
            side_effect=fake_post,
        ):
            resp = c.get(reverse("siteconfig:billing_stripe_connect_start"), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "https://connect.stripe.com/setup/test")
        self.school.refresh_from_db()
        self.assertEqual(
            self.school.settings.get("stripe_connect", {}).get("account_id"),
            "acct_new",
        )

    def test_connect_return_refreshes_status(self):
        u = self._staff_with_perm()
        self.school.settings = {"stripe_connect": {"account_id": "acct_ret"}}
        self.school.save(update_fields=["settings"])
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)

        with patch(
            "apps.billing.stripe_connect_onboarding._default_get",
            return_value=(
                200,
                {
                    "id": "acct_ret",
                    "type": "express",
                    "charges_enabled": True,
                    "payouts_enabled": True,
                    "details_submitted": True,
                },
                "{}",
            ),
        ):
            resp = c.get(reverse("siteconfig:billing_stripe_connect_return"), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        self.assertEqual(
            self.school.settings["stripe_connect"]["onboarding_status"],
            "complete",
        )
