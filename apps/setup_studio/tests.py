from django.test import TestCase

from apps.policies.models import BlueprintPack
from apps.schools.models import School
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.services import get_setup_studio_payload


class SetupStudioServiceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Setup School",
            slug="setup-school",
            subdomain="setup-school",
            country_code="CM",
            is_active=True,
        )
        BlueprintPack.objects.create(
            slug="cm-launch",
            name="Cameroon launch baseline",
            description="Regional baseline for Cameroon schools.",
            supported_country_scope=["CM"],
            default_dashboard_pack_id=1,
            default_workflow_pack_id=1,
            is_active=True,
        )

    def test_payload_persists_progress_and_blockers(self):
        payload = get_setup_studio_payload(self.school)

        self.assertIn("steps", payload)
        self.assertIn("current_step", payload)
        self.assertIn("recommended_next", payload)
        self.assertIn("preview_cards", payload)
        self.assertIn("preview_workspace", payload)
        self.assertIn("health_summary", payload)
        self.assertIn("launch_blockers", payload)
        self.assertIn("launch_orchestration", payload)
        self.assertIn("recommendations", payload)
        self.assertIn("blueprint_rankings", payload)
        self.assertIn("recommended_starter_stack", payload)
        self.assertIn("migration_path_flow", payload)
        self.assertIn("data_path_choices", payload)
        self.assertEqual(len(payload["migration_path_flow"]), 4)
        self.assertEqual(
            [s["key"] for s in payload["migration_path_flow"]],
            ["assess", "blueprint", "import", "verify"],
        )
        self.assertGreaterEqual(len(payload["launch_blockers"]), 1)
        self.assertGreaterEqual(payload["progress_percent"], 0)
        self.assertEqual(payload["recommended_next"]["key"], "plan_choice")
        self.assertTrue(payload["blueprint_rankings"])
        self.assertEqual(len(payload["data_path_choices"]), 3)
        self.assertEqual(payload["recommended_blueprint"]["title"], "Cameroon launch baseline")

        progress = SetupProgress.objects.get(school=self.school)
        self.assertEqual(progress.health_score, payload["health_score"])
        self.assertEqual(progress.launch_blockers, payload["launch_blockers"])
        self.assertEqual(progress.recommendations, payload["recommendations"])
        self.assertFalse(progress.launch_ready)

    def test_role_previews_are_present(self):
        payload = get_setup_studio_payload(self.school)
        role_codes = {item["role"] for item in payload["role_previews"]}
        self.assertEqual(role_codes, {"admin", "teacher", "parent", "finance", "student"})
        preview_titles = {item["title"] for item in payload["preview_cards"]}
        self.assertEqual(
            preview_titles,
            {"School website", "Admin shell", "Teacher dashboard", "Parent portal", "Finance console", "Student portal"},
        )
        self.assertGreaterEqual(len(payload["preview_workspace"]["surfaces"]), 6)
        self.assertEqual(len(payload["preview_workspace"]["recommended_sequence"]), 6)
        self.assertIn(payload["preview_workspace"]["preview_fidelity_level"], ("full", "partial", "none"))
        self.assertIn("preview_note", payload["preview_workspace"])
        orchestration_keys = {item["key"] for item in payload["launch_orchestration"]}
        self.assertEqual(orchestration_keys, {"preflight", "preview", "launch_control", "post_launch"})

    def test_launch_orchestration_stages_have_required_fields(self):
        """RUNMYCAMPUS §6.5: launch_orchestration stages must have key, label, detail, done, link, status."""
        payload = get_setup_studio_payload(self.school)
        for stage in payload["launch_orchestration"]:
            self.assertIn("key", stage)
            self.assertIn("label", stage)
            self.assertIn("detail", stage)
            self.assertIn("done", stage)
            self.assertIn("link", stage)
            self.assertIn("status", stage)
            self.assertIn(stage["status"], ("Ready", "Needs action"))
