from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*", "manager.runmycampus.com"], ROOT_URLCONF="config.urls")
class PackLibrariesTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com", raise_request_exception=False)
        User.objects.create_user(
            username="pack_operator",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        self.client.login(username="pack_operator", password="x" * 8)

    def test_pack_facades_render_required_pack_categories(self):
        for path, expected in {
            "/configuration/packages/": "Core School OS",
            "/configuration/workflow-packs/": "Admission Intake",
            "/configuration/dashboard-packs/": "Leadership Pulse",
            "/configuration/policy-bundles/": "Student Data Governance",
        }.items():
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=response.content[:500])
            body = response.content.decode("utf-8", errors="replace")
            self.assertIn(expected, body)
            self.assertIn("Preview", body)
            self.assertNotIn('href="#"', body)

    def test_workflow_packs_expose_trigger_condition_action_owner_and_simulation(self):
        response = self.client.get("/configuration/workflow-packs/")
        body = response.content.decode("utf-8", errors="replace")

        self.assertIn("Trigger", body)
        self.assertIn("Condition", body)
        self.assertIn("Action", body)
        self.assertIn("Owner", body)
        self.assertIn("Simulation", body)
