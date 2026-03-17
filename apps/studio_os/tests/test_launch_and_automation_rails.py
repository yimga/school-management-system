"""
Verify Launch Studio (§4.5) and Automation Studio (§5.7) rail views resolve and return 200 for staff.
SOT §4.5 select plan; §5.7 dependency graph, replay/rollback, health, conflict detection, staged activation,
visual builder, natural-language workflow, simulation engine.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

LAUNCH_RAIL_VIEWS = [
    ("studio_os:launch_select_plan", "§4.5 Select plan"),
]

AUTOMATION_RAIL_VIEWS = [
    ("studio_os:automation_dependency_graph", "§5.7 dependency graph"),
    ("studio_os:automation_replay_rollback", "§5.7 replay/rollback"),
    ("studio_os:automation_workflow_health", "§5.7 health analytics"),
    ("studio_os:automation_conflict_detection", "§5.7 conflict detection"),
    ("studio_os:automation_staged_activation", "§5.7 staged activation"),
    ("studio_os:automation_visual_builder", "§5.7 visual builder"),
    ("studio_os:automation_natural_language_workflow", "§5.7 AI workflow generation"),
    ("studio_os:automation_simulation_engine", "§5.7 simulation engine"),
]


class StudioLaunchAndAutomationRailsTests(TestCase):
    """Verify Launch and Automation rail views are wired and return 200 for staff."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="studio-rails-user",
            email="studio-rails@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

    def test_launch_select_plan_returns_200_for_staff(self):
        """§4.5 Select plan: view and URL wired; returns 200."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch_select_plan")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, "launch_select_plan should return 200 for staff")

    def test_automation_rail_views_return_200_for_staff(self):
        """§5.7 Automation rail placeholders: all resolve and return 200 for staff."""
        self.client.force_login(self.user)
        for name, _label in AUTOMATION_RAIL_VIEWS:
            with self.subTest(view=name):
                url = reverse(name)
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code, 200,
                    f"{name} should return 200 for staff",
                )
