from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.compliance.models import RegionFeatureCompliance
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class SeedComplianceBaselineCommandTests(TestCase):
    def test_seed_command_enables_strict_compliance_auditor(self):
        region = RegionConfig.get_default()
        school = School.objects.create(
            name="Baseline School",
            slug="baseline-school",
            subdomain="baseline-school",
            is_active=True,
            default_region=region,
            settings={},
        )

        call_command("seed_compliance_baseline")

        school.refresh_from_db()
        self.assertIn("tenant_policy_pack", school.settings)
        self.assertIn("tenant_compiled_config", school.settings)
        self.assertIn("tenant_config_metadata", school.settings)
        self.assertGreater(RegionFeatureCompliance.objects.count(), 0)

        out = StringIO()
        call_command("compliance_auditor", "--strict", "--min-score", "70", stdout=out)
        self.assertIn("Overall score:", out.getvalue())
