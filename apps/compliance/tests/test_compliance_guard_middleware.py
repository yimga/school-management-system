import json

from django.test import RequestFactory, TestCase

from apps.compliance.middleware import ComplianceGuardMiddleware
from apps.compliance.models import RegionFeatureCompliance
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class ComplianceGuardMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ComplianceGuardMiddleware(lambda request: None)
        self.region = RegionConfig.objects.create(code="CGR", name="Compliance Guard Region")
        self.school = School.objects.create(
            name="Compliance Guard School",
            slug="compliance-guard-school",
            subdomain="compliance-guard-school",
            default_region=self.region,
            is_active=True,
        )

    def test_blocks_restricted_oneroster_api_path(self):
        RegionFeatureCompliance.objects.create(
            region=self.region,
            feature_code="OneRoster_Interop",
            status=RegionFeatureCompliance.Status.RESTRICTED,
        )
        request = self.factory.get("/api/oneroster/v1p1/students")
        request.school = self.school

        response = self.middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload.get("error"), "compliance_restricted")
        self.assertEqual(payload.get("feature"), "OneRoster_Interop")

    def test_blocks_restricted_lti_path_with_forbidden_html(self):
        RegionFeatureCompliance.objects.create(
            region=self.region,
            feature_code="LTI13_Interop",
            status=RegionFeatureCompliance.Status.DISABLED,
        )
        request = self.factory.get("/lti/launch/12/")
        request.school = self.school

        response = self.middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        self.assertIn("LTI13_Interop", response.content.decode("utf-8"))

    def test_allows_when_no_matching_rule(self):
        request = self.factory.get("/api/oneroster/v1p1/students")
        request.school = self.school

        response = self.middleware.process_request(request)

        self.assertIsNone(response)
