import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.compliance.middleware import COMPLIANCE_GUARD_PATH_MAP
from apps.compliance.models import RegionFeatureCompliance
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class ComplianceAuditorCommandTests(TestCase):
    def setUp(self):
        self.region_us, _ = RegionConfig.objects.get_or_create(
            code="USA",
            defaults={
                "name": "United States",
                "default_language": "en",
                "timezone": "America/New_York",
                "date_format": "MM/DD/YYYY",
                "grading_scale": "0-100",
                "default_currency": "USD",
            },
        )
        self.region_cmr, _ = RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={
                "name": "Cameroon",
                "default_language": "en",
                "timezone": "Africa/Douala",
                "date_format": "DD/MM/YYYY",
                "grading_scale": "0-20",
                "default_currency": "XAF",
            },
        )

    def _core_feature_codes(self):
        return sorted({str(code).strip() for code in COMPLIANCE_GUARD_PATH_MAP.values() if str(code).strip()})

    def test_command_json_outputs_region_and_school_scorecards(self):
        School.objects.create(
            name="US Ready School",
            slug="us-ready-school",
            subdomain="us-ready-school",
            is_active=True,
            default_region=self.region_us,
            settings={
                "tenant_policy_pack": {"code": "US", "version": "2026.1"},
                "tenant_compiled_config": {"default_language": "en"},
                "tenant_config_metadata": {"default_language": {"source": "tenant_override"}},
            },
        )
        School.objects.create(
            name="CMR Incomplete School",
            slug="cmr-incomplete-school",
            subdomain="cmr-incomplete-school",
            is_active=True,
            default_region=self.region_cmr,
            settings={},
        )

        for feature_code in self._core_feature_codes():
            RegionFeatureCompliance.objects.create(
                region=self.region_us,
                feature_code=feature_code,
                status=RegionFeatureCompliance.Status.ENABLED,
            )

        out = StringIO()
        call_command("compliance_auditor", "--json", stdout=out)
        payload = json.loads(out.getvalue())

        self.assertIn("score", payload)
        self.assertIn("checks", payload)
        self.assertIn("regions", payload)
        self.assertIn("schools", payload)
        self.assertIn("USA", payload["regions"])
        self.assertIn("CMR", payload["regions"])
        self.assertEqual(payload["regions"]["USA"]["core_feature_missing_count"], 0)
        self.assertGreater(payload["regions"]["CMR"]["core_feature_missing_count"], 0)

        by_slug = {item["school_slug"]: item for item in payload["schools"]}
        self.assertIn("us-ready-school", by_slug)
        self.assertIn("cmr-incomplete-school", by_slug)
        self.assertGreater(by_slug["us-ready-school"]["score"], by_slug["cmr-incomplete-school"]["score"])

    def test_command_strict_raises_when_score_below_threshold(self):
        School.objects.create(
            name="No Region School",
            slug="no-region-school",
            subdomain="no-region-school",
            is_active=True,
            default_region=None,
            settings={},
        )
        with self.assertRaises(CommandError):
            call_command("compliance_auditor", "--strict", "--min-score", "99")
