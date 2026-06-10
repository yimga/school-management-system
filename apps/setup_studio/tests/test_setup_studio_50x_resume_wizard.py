"""Setup Studio 50X — resume wizard URL."""

from django.test import TestCase
from django.urls import reverse

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.zero_friction import get_zero_friction_payload


class SetupStudioResumeWizardTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Resume School",
            slug="resume-school",
            subdomain="resume-school",
            country_code="CM",
            is_active=True,
        )

    def test_resume_url_uses_named_route_when_wizard_state(self):
        progress, _ = SetupProgress.objects.get_or_create(school=self.school)
        progress.step_state = {
            "wizards": {
                "parent_payment_setup": {
                    "current_step": 1,
                    "last_modified": "2026-06-09T12:00:00+00:00",
                    "completed": [],
                }
            }
        }
        progress.save(update_fields=["step_state"])
        data = get_zero_friction_payload(self.school)
        url = data["actions"]["resume_wizard_url"]
        if url:
            self.assertTrue(url.startswith("/"))
            expected = reverse(
                "setup_studio:tenant_wizard",
                kwargs={"wizard_key": "parent_payment_setup"},
            )
            self.assertEqual(url, expected)
