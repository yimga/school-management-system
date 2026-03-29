"""GET /api/v1/config/education-dna includes report-platform bundle read-model fields."""

import json

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.api.views_v1 import EducationDNAView
from apps.platform_runtime.models import PlatformReportPlatformSkuDefault
from apps.schools.models import School
from apps.siteconfig.billing_sku_registry import (
    REPORT_PLATFORM_SKU_ADVANCED,
    REPORT_PLATFORM_SKU_STANDARD,
)


class EducationDnaReportPlatformReadModelTests(TestCase):
    def setUp(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug=REPORT_PLATFORM_SKU_ADVANCED
        )
        self.school = School.objects.create(
            name="Edu DNA RP",
            slug="edu-dna-rp",
            subdomain="edu-dna-rp",
            is_active=True,
            report_platform_bundle_slug=REPORT_PLATFORM_SKU_STANDARD,
        )
        self.user = User.objects.create_user(
            username="edu_dna_rp",
            email="edu_dna_rp@example.com",
            password="secret",
        )

    def _get(self):
        rf = RequestFactory()
        req = rf.get("/api/v1/config/education-dna")
        req.user = self.user
        req.school = self.school
        return EducationDNAView.as_view()(req)

    def test_education_dna_includes_report_platform_slugs(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertEqual(data["report_platform_bundle_slug"], REPORT_PLATFORM_SKU_STANDARD)
        self.assertEqual(
            data["effective_report_platform_bundle"], REPORT_PLATFORM_SKU_STANDARD
        )

    def test_education_dna_effective_falls_back_to_operator_default(self):
        self.school.report_platform_bundle_slug = ""
        self.school.save(update_fields=["report_platform_bundle_slug"])
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertEqual(data["report_platform_bundle_slug"], "")
        self.assertEqual(
            data["effective_report_platform_bundle"], REPORT_PLATFORM_SKU_ADVANCED
        )
