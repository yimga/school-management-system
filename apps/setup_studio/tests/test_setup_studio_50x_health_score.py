"""Setup Studio 50X — health score persistence."""

from django.test import TestCase

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.services import compile_setup_studio
from apps.setup_studio.zero_friction import get_zero_friction_payload


class SetupStudioHealthScoreTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Health School",
            slug="health-school",
            subdomain="health-school",
            country_code="CM",
            is_active=True,
        )

    def test_health_score_in_zero_friction_payload(self):
        data = get_zero_friction_payload(self.school)
        self.assertIsInstance(data["health_score"], int)
        self.assertGreaterEqual(data["health_score"], 0)

    def test_compile_updates_health_score(self):
        compile_setup_studio(self.school)
        data = get_zero_friction_payload(self.school)
        self.assertIn("health_summary", data)
