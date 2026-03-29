"""GET /api/v1/me/schools includes report-platform bundle read-model fields."""

import json

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.api.views_v1 import MeSchoolsView
from apps.platform_runtime.models import PlatformReportPlatformSkuDefault
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.billing_sku_registry import (
    REPORT_PLATFORM_SKU_ADVANCED,
    REPORT_PLATFORM_SKU_STANDARD,
)


class MeSchoolsReportPlatformReadModelTests(TestCase):
    def setUp(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug=REPORT_PLATFORM_SKU_ADVANCED
        )
        self.school = School.objects.create(
            name="Me schools RP",
            slug="me-schools-rp",
            subdomain="me-schools-rp",
            is_active=True,
            report_platform_bundle_slug=REPORT_PLATFORM_SKU_STANDARD,
        )
        self.user = User.objects.create_user(
            username="me_schools_rp",
            email="me_schools_rp@example.com",
            password="secret",
        )
        SchoolMembership.objects.create(
            school=self.school,
            user=self.user,
            role=User.Role.TEACHER,
            is_primary=True,
        )

    def test_me_schools_includes_report_platform_slugs(self):
        self.assertTrue(self.client.login(username="me_schools_rp", password="secret"))
        r = self.client.get("/api/v1/me/schools")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content.decode("utf-8"))
        self.assertEqual(len(data["schools"]), 1)
        row = data["schools"][0]
        self.assertEqual(row["report_platform_bundle_slug"], REPORT_PLATFORM_SKU_STANDARD)
        self.assertEqual(
            row["effective_report_platform_bundle"], REPORT_PLATFORM_SKU_STANDARD
        )

    def test_me_schools_effective_falls_back_to_operator_default(self):
        self.school.report_platform_bundle_slug = ""
        self.school.save(update_fields=["report_platform_bundle_slug"])
        self.assertTrue(self.client.login(username="me_schools_rp", password="secret"))
        r = self.client.get("/api/v1/me/schools")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content.decode("utf-8"))
        row = data["schools"][0]
        self.assertEqual(row["report_platform_bundle_slug"], "")
        self.assertEqual(
            row["effective_report_platform_bundle"], REPORT_PLATFORM_SKU_ADVANCED
        )


class MeSchoolsChildSchoolsReportPlatformTests(TestCase):
    """child_schools[] includes the same report-platform read-model keys as schools[]."""

    def setUp(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug=REPORT_PLATFORM_SKU_ADVANCED
        )
        self.parent = School.objects.create(
            name="Parent campus",
            slug="parent-campus",
            subdomain="parent-campus",
            is_active=True,
            report_platform_bundle_slug="",
        )
        self.child = School.objects.create(
            name="Child campus",
            slug="child-campus",
            subdomain="child-campus",
            is_active=True,
            parent_school=self.parent,
            report_platform_bundle_slug=REPORT_PLATFORM_SKU_STANDARD,
        )
        self.user = User.objects.create_user(
            username="me_schools_parent",
            email="me_schools_parent@example.com",
            password="secret",
        )
        SchoolMembership.objects.create(
            school=self.parent,
            user=self.user,
            role=User.Role.TEACHER,
            is_primary=True,
        )

    def test_child_schools_include_report_platform_fields(self):
        rf = RequestFactory()
        req = rf.get("/api/v1/me/schools")
        req.user = self.user
        req.school = self.parent
        resp = MeSchoolsView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertEqual(len(data["child_schools"]), 1)
        row = data["child_schools"][0]
        self.assertEqual(row["school_id"], str(self.child.id))
        self.assertEqual(row["report_platform_bundle_slug"], REPORT_PLATFORM_SKU_STANDARD)
        self.assertEqual(
            row["effective_report_platform_bundle"], REPORT_PLATFORM_SKU_STANDARD
        )
