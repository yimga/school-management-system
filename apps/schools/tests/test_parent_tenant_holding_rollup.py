"""Parent-tenant dashboard surfaces B4 multi-currency rollups."""
from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models_platform_catalog import Plan

User = get_user_model()

_T_HOST = "holding-ui.runmycampus.com"

PRICES = {
    "sub-ui-a": {"total": Decimal("120.00"), "currency_code": "USD"},
    "sub-ui-b": {"total": Decimal("8000.00"), "currency_code": "NGN"},
}


def _fake_price(school, plan, **kwargs):
    return PRICES.get(school.slug, {"total": Decimal("0.00"), "currency_code": "USD"})


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST],
    CONVERSION_LOCK_STRICT=False,
    CONVERSION_LOCK_ALL_SCHOOLS=False,
    DISABLE_SCHOOL_ACTIVATION_GATE=True,
)
class ParentTenantHoldingRollupViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Pro UI",
            slug="pro-ui-b4",
            base_price=Decimal("100.00"),
            is_active=True,
        )
        cls.holding = School.objects.create(
            name="Holding UI",
            slug="holding-ui",
            subdomain="holding-ui",
            is_active=True,
            is_approved=True,
        )
        for slug in ("sub-ui-a", "sub-ui-b"):
            School.objects.create(
                name=slug,
                slug=slug,
                subdomain=slug,
                is_active=True,
                parent_school=cls.holding,
                plan=cls.plan,
            )
        cls.admin = User.objects.create_user(
            username="holding-ui-admin",
            password="Test1234!",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=cls.admin,
            school=cls.holding,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)
        self.client.login(username="holding-ui-admin", password="Test1234!")
        session = self.client.session
        session["school_id"] = str(self.holding.id)
        session["mfa_verified"] = True
        session.save()

    @mock.patch("apps.billing.services.compute_subscription_price_for_school", _fake_price)
    def test_dashboard_renders_currency_buckets(self):
        url = reverse("organization_network_dashboard", urlconf="config.tenant_urls")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Honest multi-currency rollup")
        self.assertContains(response, "USD")
        self.assertContains(response, "NGN")
        self.assertContains(response, "120.00")
        self.assertContains(response, "8000.00")

    def test_forbidden_without_child_schools(self):
        from django.test import RequestFactory

        from apps.schools.parent_tenant_views import parent_tenant_dashboard

        lone = School.objects.create(
            name="Lone RF",
            slug="lone-rf",
            subdomain="lone-rf",
            is_active=True,
        )
        user = User.objects.create_user(
            username="lone-rf-admin",
            password="Test1234!",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        request = RequestFactory().get("/organization/network/")
        request.user = user
        request.session = {}
        request.school = lone
        response = parent_tenant_dashboard(request)
        self.assertEqual(response.status_code, 403)
