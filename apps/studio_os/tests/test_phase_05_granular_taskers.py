"""
Phase 5 granular spec: preview routes, simulation native canvas, Launch rail coherence.
Maps to docs/phase_audit/PHASE_05_STUDIO_OS_AUDIT.md §0.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

User = get_user_model()


class Phase05GranularTaskersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="phase5-granular",
            email="p5g@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)

    def test_preview_routes_resolve_for_unified_preview_pipeline(self):
        """Preview fragments: Studio + siteconfig form preview."""
        self.assertTrue(reverse("studio_os:preview"))
        try:
            reverse("siteconfig:preview_from_form")
        except NoReverseMatch:
            self.fail("siteconfig:preview_from_form must resolve for preview pipeline")

    def test_automation_simulation_pane_uses_native_explainer_not_full_canvas_iframe(self):
        """Setup/simulation awareness: simulation pane is native explainer (§0 tasker)."""
        url = reverse("studio_os:automation") + "?pane=simulation"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            b'id="studio-automation-iframe"',
            response.content,
            "Simulation pane should not use the full-canvas automation iframe",
        )

    def test_launch_studio_rail_includes_guided_onboarding_pane(self):
        """Launch/setup flows: rail exposes onboarding wizard pane (low-click)."""
        response = self.client.get(reverse("studio_os:launch"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pane=onboarding")
