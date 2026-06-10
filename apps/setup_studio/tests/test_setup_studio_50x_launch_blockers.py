"""Setup Studio 50X — launch blocker remediation."""

from django.test import TestCase

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.zero_friction import what_is_blocking_launch


class SetupStudioLaunchBlockersTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Blocker School",
            slug="blocker-school",
            subdomain="blocker-school",
            country_code="CM",
            is_active=True,
        )

    def test_remediation_auto_fix_when_blockers(self):
        data = what_is_blocking_launch(self.school)
        self.assertIn("remediation", data)
        rem = data["remediation"]
        self.assertIn("remediation_available", rem)

    def test_blockers_list_shape(self):
        data = what_is_blocking_launch(self.school)
        self.assertIn("blockers", data)
        self.assertIsInstance(data["blockers"], list)
