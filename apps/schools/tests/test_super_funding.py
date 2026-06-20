import os
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.schools.advancement_services import advancement_enabled
from apps.schools.models import AdvancementDonor, AdvancementGift, School

MANAGER_HOST = "manager.runmycampus.com"


class AdvancementEnabledGateTests(TestCase):
    """The zero-regression gate: enabled-by-default, off only on explicit False."""

    def setUp(self):
        self.school = School.objects.create(
            name="Gate School", slug="gate-school",
            subdomain="gate-school", is_active=True,
        )

    def test_enabled_by_default(self):
        self.assertTrue(advancement_enabled(self.school))

    def test_disabled_only_on_explicit_false(self):
        self.school.features = {"advancement": False}
        self.school.save(update_fields=["features"])
        self.assertFalse(advancement_enabled(self.school))

    def test_truthy_or_missing_key_stays_enabled(self):
        self.school.features = {"advancement": True}
        self.school.save(update_fields=["features"])
        self.assertTrue(advancement_enabled(self.school))
        self.school.features = {}
        self.school.save(update_fields=["features"])
        self.assertTrue(advancement_enabled(self.school))

    def test_none_school_is_false(self):
        self.assertFalse(advancement_enabled(None))


@override_settings(ALLOWED_HOSTS=["*"], OPERATOR_MFA_REQUIRED_ON_MANAGER=False)
class SuperFundingOverviewTests(TestCase):
    """A superuser force-logged-in on the manager host with MULTI_TENANT_BASE_DOMAIN
    patched, exercising super_funding_overview's @require_platform_scope contract.
    OPERATOR_MFA_REQUIRED_ON_MANAGER is disabled so OperatorMfaRequiredMiddleware
    doesn't bounce the operator to /mfa/setup/ before the view runs (the MFA flow is
    covered by its own tests; here we assert the funding rollup itself)."""

    def setUp(self):
        self.school = School.objects.create(
            name="Funding School", slug="funding-school",
            subdomain="funding-school", is_active=True,
        )
        donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Big Donor"
        )
        AdvancementGift.objects.create(
            donor=donor, amount=Decimal("500.00"), currency="USD",
            received_at=timezone.now().date(),
        )
        AdvancementGift.objects.create(
            donor=donor, amount=Decimal("300.00"), currency="USD",
            received_at=timezone.now().date(),
        )
        self.op = get_user_model().objects.create_user(
            username="funding_op", email="op@example.com", password="x",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.op)
        cache.clear()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_operator_can_view_cross_tenant_rollup(self):
        resp = self.client.get(
            reverse("super:funding_overview"), HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Funding School")
        self.assertContains(resp, "800")  # 500 + 300 cash raised across tenants

    def test_unauthenticated_is_blocked(self):
        resp = Client().get(
            reverse("super:funding_overview"), HTTP_HOST=MANAGER_HOST
        )
        self.assertIn(resp.status_code, (302, 403))
