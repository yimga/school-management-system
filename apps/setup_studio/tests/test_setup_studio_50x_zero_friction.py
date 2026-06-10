"""Setup Studio 50X zero-friction tests."""

from django.test import TestCase

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.zero_friction import (
    apply_recommended_setup,
    get_zero_friction_payload,
    merge_persisted_wizard_state,
    what_is_blocking_launch,
)


class SetupStudio50XTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="50X School",
            slug="fiftyx-school",
            subdomain="fiftyx-school",
            country_code="CM",
            is_active=True,
        )

    def test_merge_preserves_wizards_namespace(self):
        launch = {"institution_basics": {"done": False}}
        merged = merge_persisted_wizard_state(
            {"wizards": {"parent_payment_setup": {"step": 2}}},
            launch,
        )
        self.assertIn("wizards", merged)
        self.assertEqual(merged["wizards"]["parent_payment_setup"]["step"], 2)

    def test_zero_friction_payload_has_health(self):
        data = get_zero_friction_payload(self.school)
        self.assertIn("health_score", data)
        self.assertIn("launch_blockers", data)

    def test_apply_recommended_setup_idempotent(self):
        first = apply_recommended_setup(self.school)
        second = apply_recommended_setup(self.school)
        self.assertTrue(first["ok"])
        self.assertEqual(first["next_step_key"], second["next_step_key"])

    def test_what_is_blocking_launch_remediation_shape(self):
        data = what_is_blocking_launch(self.school)
        self.assertIn("remediation", data)
        self.assertIn("error_type", data["remediation"])

    def test_compile_setup_studio_preserves_wizards(self):
        from apps.setup_studio.services import compile_setup_studio

        progress, _ = SetupProgress.objects.get_or_create(school=self.school)
        progress.step_state = {"wizards": {"demo": {"current_step": 1}}}
        progress.save(update_fields=["step_state"])
        compile_setup_studio(self.school)
        progress.refresh_from_db()
        self.assertIn("wizards", progress.step_state)
        self.assertIn("demo", progress.step_state["wizards"])
