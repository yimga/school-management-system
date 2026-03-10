from django.test import TestCase

from apps.schools.models import School
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.services import get_setup_studio_payload


class SetupStudioServiceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Setup School",
            slug="setup-school",
            subdomain="setup-school",
            is_active=True,
        )

    def test_payload_persists_progress_and_blockers(self):
        payload = get_setup_studio_payload(self.school)

        self.assertIn("steps", payload)
        self.assertIn("current_step", payload)
        self.assertIn("recommended_next", payload)
        self.assertIn("preview_cards", payload)
        self.assertIn("health_summary", payload)
        self.assertIn("launch_blockers", payload)
        self.assertIn("recommendations", payload)
        self.assertGreaterEqual(len(payload["launch_blockers"]), 1)
        self.assertGreaterEqual(payload["progress_percent"], 0)
        self.assertEqual(payload["recommended_next"]["key"], "plan_choice")

        progress = SetupProgress.objects.get(school=self.school)
        self.assertEqual(progress.health_score, payload["health_score"])
        self.assertEqual(progress.launch_blockers, payload["launch_blockers"])
        self.assertEqual(progress.recommendations, payload["recommendations"])
        self.assertFalse(progress.launch_ready)

    def test_role_previews_are_present(self):
        payload = get_setup_studio_payload(self.school)
        role_codes = {item["role"] for item in payload["role_previews"]}
        self.assertEqual(role_codes, {"admin", "teacher", "parent"})
        preview_titles = {item["title"] for item in payload["preview_cards"]}
        self.assertEqual(preview_titles, {"School website", "Admin shell", "Teacher dashboard", "Parent portal"})
