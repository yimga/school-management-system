"""Setup Studio 50X — recommended setup apply."""

from django.test import TestCase

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.zero_friction import apply_recommended_setup


class SetupStudioRecommendedSetupTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Rec School",
            slug="rec-school",
            subdomain="rec-school",
            country_code="CM",
            is_active=True,
        )

    def test_recommended_setup_returns_next_url(self):
        result = apply_recommended_setup(self.school, actor_id=1)
        self.assertTrue(result["ok"])
        self.assertIn("next_url", result)

    def test_recommended_setup_stable(self):
        a = apply_recommended_setup(self.school)
        b = apply_recommended_setup(self.school)
        self.assertEqual(a["next_step_key"], b["next_step_key"])
