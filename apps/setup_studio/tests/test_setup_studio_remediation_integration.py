"""Setup Studio remediation integration."""

from django.test import TestCase

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.zero_friction import what_is_blocking_launch


class SetupStudioRemediationIntegrationTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Rem School",
            slug="rem-school",
            subdomain="rem-school",
            country_code="CM",
            is_active=True,
        )

    def test_remediation_payload_tenant_safe(self):
        data = what_is_blocking_launch(self.school)
        remediation = data["remediation"]
        self.assertIn("human_readable_explanation", remediation)
        self.assertNotIn("traceback", str(remediation).lower())
