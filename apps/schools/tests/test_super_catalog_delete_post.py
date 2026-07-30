"""
POST integration tests: super catalog delete confirms remove rows (302 + DB gone).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.siteconfig.models_feature_controls import FeatureToggleDefinition
from apps.test_utils.http_clients import login_manager_client  # noqa: E402
from apps.siteconfig.models_global_experience import GradingScaleConfig
from apps.siteconfig.models_platform_catalog import (
    CountryMultiplier,
    Plan,
    PlanAddon,
    RegionConfig,
)


@override_settings(ALLOWED_HOSTS=["*"])
class SuperCatalogDeletePostTests(TestCase):
    """POST confirm=yes to super delete URLs removes rows when constraints allow."""

    host = "manager.runmycampus.com"

    def setUp(self):
        self.user = User.objects.create_user(
            username="super_delete_post",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        # Manager-host operator POSTs: bind the manager session with confirmed +
        # verified MFA, else the delete POST bounces 302 to /authentication/mfa/
        # setup/ and the row is never deleted.
        self.client = login_manager_client(self.user, password="testpass123")

    def _post_delete(self, url_name: str, *, kwargs: dict | None = None):
        if kwargs is None:
            kwargs = {}
        url = reverse(url_name, kwargs=kwargs)
        return self.client.post(
            url,
            {"confirm": "yes"},
            HTTP_HOST=self.host,
        )

    def test_post_delete_plan(self):
        plan = Plan.objects.create(
            name="Delete Me Plan",
            slug="delete-me-plan-post",
            billing_model=Plan.BillingModel.FLAT,
            is_active=True,
        )
        pk = plan.pk
        response = self._post_delete("super:plan_delete", kwargs={"pk": pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("super:plans_list"), response["Location"])
        self.assertFalse(Plan.objects.filter(pk=pk).exists())

    def test_post_delete_plan_without_confirm_does_not_remove(self):
        suffix = uuid.uuid4().hex[:8]
        plan = Plan.objects.create(
            name="Keep Me Plan",
            slug=f"keep-plan-{suffix}",
            billing_model=Plan.BillingModel.FLAT,
            is_active=True,
        )
        pk = plan.pk
        url = reverse("super:plan_delete", kwargs={"pk": pk})
        response = self.client.post(url, {}, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Plan.objects.filter(pk=pk).exists())

    def test_post_delete_plan_addon(self):
        suffix = uuid.uuid4().hex[:8]
        addon = PlanAddon.objects.create(
            code=f"del-addon-{suffix}",
            name="Delete Me Addon",
            price=Decimal("0.00"),
            is_active=True,
        )
        pk = addon.pk
        response = self._post_delete("super:plan_addon_delete", kwargs={"pk": pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("super:plans_list"), response["Location"])
        self.assertFalse(PlanAddon.objects.filter(pk=pk).exists())

    def test_post_delete_country_multiplier(self):
        # ISO-like unique code (max_length=3 on model)
        cc = f"Q{uuid.uuid4().hex[:2].upper()}"
        row = CountryMultiplier.objects.create(
            country_code=cc,
            zone=CountryMultiplier.Zone.B,
            multiplier=Decimal("1.0000"),
            name="Delete test multiplier",
            is_active=True,
        )
        pk = row.pk
        response = self._post_delete(
            "super:country_multiplier_delete", kwargs={"pk": pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("super:country_multipliers_list"), response["Location"]
        )
        self.assertFalse(CountryMultiplier.objects.filter(pk=pk).exists())

    def test_post_delete_grading_scale(self):
        rcode = f"G{uuid.uuid4().hex[:8].upper()}"[:10]
        region = RegionConfig.objects.create(
            code=rcode,
            name="Grading delete test region",
            default_language="en",
            timezone="UTC",
        )
        scale = GradingScaleConfig.objects.create(
            region=region,
            scale_type="0-100",
            min_score=Decimal("0"),
            max_score=Decimal("100"),
            display_format="{score:.0f}",
            grade_a_min=Decimal("90"),
            grade_b_min=Decimal("80"),
            grade_c_min=Decimal("70"),
            grade_d_min=Decimal("60"),
            grade_f_min=Decimal("0"),
        )
        pk = scale.pk
        response = self._post_delete("super:grading_delete", kwargs={"pk": pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("super:grading_list"), response["Location"])
        self.assertFalse(GradingScaleConfig.objects.filter(pk=pk).exists())

    def test_post_delete_feature_toggle_definition(self):
        row, _ = FeatureToggleDefinition.objects.get_or_create(
            key="delete_me_toggle_post",
            defaults={
                "label": "Delete me toggle",
                "scope": FeatureToggleDefinition.Scope.GLOBAL,
            },
        )
        pk = row.pk
        response = self._post_delete(
            "super:feature_toggle_delete", kwargs={"pk": pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("super:feature_toggles_list"), response["Location"]
        )
        self.assertFalse(FeatureToggleDefinition.objects.filter(pk=pk).exists())

    def test_post_delete_region_without_school_reference(self):
        rcode = f"R{uuid.uuid4().hex[:8].upper()}"[:10]
        region = RegionConfig.objects.create(
            code=rcode,
            name="Region delete post test",
            default_language="en",
            timezone="UTC",
        )
        code = region.code
        response = self._post_delete(
            "super:region_delete", kwargs={"code": code}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("super:regions_list"), response["Location"])
        self.assertFalse(RegionConfig.objects.filter(pk=code).exists())
