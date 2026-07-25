"""North Star SLICE 2 — DB grading scales / bands (operator page + validation + service)."""

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.evals.grading_scale_service import (
    get_effective_grading_scale_for_school,
    get_grade_band_for_normalized,
    get_grade_band_for_score,
)
from apps.evals.models import GradingScale, GradingScaleBand
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client

_T_HOST = "gsb2ns.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class GradingScaleBandsSlice2Tests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Slice2",
            slug="slice-2-plan",
            included_features=["core"],
            is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code="G2",
            name="Slice2land",
            timezone="UTC",
            default_currency="USD",
        )
        cls.school = School.objects.create(
            name="Grading Bands School",
            slug="gsb2ns",
            subdomain="gsb2ns",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
            settings={"grading_scale": "0-20"},
        )
        cls.scale_other = GradingScale.objects.create(
            school=cls.school,
            code="legacy",
            name="Non default",
            scale_type=GradingScale.ScaleType.NUMERIC_0_20,
            is_default=False,
            is_active=True,
        )
        cls.scale = GradingScale.objects.create(
            school=cls.school,
            code="cam-020",
            name="Cameroon 0–20",
            region=cls.region,
            scale_type=GradingScale.ScaleType.NUMERIC_0_20,
            is_default=True,
            is_active=True,
        )
        GradingScaleBand.objects.create(
            grading_scale=cls.scale,
            sort_order=0,
            min_score="0",
            max_score="10",
            label="Developing",
            band_weight=100,
            normalized_min="0",
            normalized_max="0.499999",
        )
        GradingScaleBand.objects.create(
            grading_scale=cls.scale,
            sort_order=1,
            min_score="10",
            max_score="20",
            label="Strong",
            band_weight=100,
            grade_point="4",
            normalized_min="0.5",
            normalized_max="1",
        )

    def test_service_prefers_default_scale(self):
        eff = get_effective_grading_scale_for_school(self.school)
        self.assertEqual(eff.pk, self.scale.pk)

    def test_normalized_maps_to_band(self):
        b = get_grade_band_for_normalized(self.scale, "0.75")
        self.assertIsNotNone(b)
        self.assertEqual(b.label, "Strong")

    def test_score_maps_to_band(self):
        b = get_grade_band_for_score(self.scale, Decimal("15"))
        self.assertEqual(b.label, "Strong")

    def test_overlap_blocked(self):
        with self.assertRaises(ValidationError):
            band = GradingScaleBand(
                grading_scale=self.scale,
                sort_order=9,
                min_score="5",
                max_score="12",
                label="Overlap",
                normalized_min="0.2",
                normalized_max="0.3",
            )
            band.save()

    def test_min_gt_max_blocked(self):
        with self.assertRaises(ValidationError):
            band = GradingScaleBand(
                grading_scale=self.scale_other,
                sort_order=0,
                min_score="15",
                max_score="10",
                label="Bad",
                normalized_min="0",
                normalized_max="1",
            )
            band.save()

    def test_operator_page_renders_bands_table(self):
        u = User.objects.create_user(
            username=f"adm_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        c = login_tenant_admin_client(
            u, password="x" * 8, host=_T_HOST, school=self.school
        )
        url = reverse("siteconfig:grading_scale_bands", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:600])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-cp-evidence-surface="grading-scale-bands"', body)
        self.assertIn("Developing", body)
        self.assertIn("Strong", body)

    def test_superuser_sees_admin_fallback_after_related_links(self):
        u = User.objects.create_user(
            username=f"su_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        c = login_tenant_admin_client(
            u, password="x" * 8, host=_T_HOST, school=self.school
        )
        url = reverse("siteconfig:grading_scale_bands", urlconf="config.tenant_urls")
        body = c.get(url).content.decode("utf-8", errors="replace")
        idx_related = body.find("Configuration control center")
        idx_adv = body.find("Advanced (Django admin)")
        self.assertNotEqual(idx_related, -1)
        self.assertNotEqual(idx_adv, -1)
        self.assertLess(idx_related, idx_adv)

    def test_non_superuser_no_admin_fallback_block(self):
        u = User.objects.create_user(
            username=f"nosu_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=False,
        )
        c = login_tenant_admin_client(
            u, password="x" * 8, host=_T_HOST, school=self.school
        )
        url = reverse("siteconfig:grading_scale_bands", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:300])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertNotIn("Advanced (Django admin)", body)

    def test_teacher_forbidden(self):
        tu = User.objects.create_user(
            username=f"t_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        # Arm as a genuine tenant member (TEACHER) so the request clears the
        # tenant-host membership guard and reaches the view, which must then
        # forbid a teacher from grading-scale configuration.
        c = login_tenant_admin_client(
            tu, password="x" * 8, host=_T_HOST, school=self.school, role="TEACHER"
        )
        url = reverse("siteconfig:grading_scale_bands", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 403)
