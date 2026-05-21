"""Phase 5 — Experience Studio three-pane workbench and context links."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Permission

User = get_user_model()


class ExperienceStudioWorkbenchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="exp-wb-user",
            email="exp-wb@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.user.feature_permissions.add(manage_perm)

    def test_experience_studio_renders_workbench_when_theme_in_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("studio_os:experience"))
        self.assertEqual(response.status_code, 200)
        if b"data-rmc-studio-workspace" in response.content:
            self.assertIn(b'data-studio-workspace-mode="experience"', response.content)
            self.assertIn(b"data-rmc-studio-workspace-main", response.content)

    def test_automation_rail_surfaces_conflict_detection_link(self):
        self.client.force_login(self.user)
        overview = self.client.get(reverse("studio_os:automation") + "?pane=overview")
        self.assertEqual(overview.status_code, 200)
        body = overview.content.decode("utf-8")
        self.assertIn("Review conflict detection", body)
        self.assertIn("pane=conflict", body)

    def test_automation_conflict_pane_omits_rail_cta_duplicate(self):
        self.client.force_login(self.user)
        conflict = self.client.get(reverse("studio_os:automation") + "?pane=conflict")
        self.assertEqual(conflict.status_code, 200)
        self.assertNotIn(
            "Review conflict detection",
            conflict.content.decode("utf-8"),
        )

    # v3.54.0 — workbench context column is a real context column.
    def test_experience_workbench_context_renders_when_workspace_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("studio_os:experience"))
        self.assertEqual(response.status_code, 200)
        body = response.content
        if b"data-rmc-studio-workspace" in body:
            # The new workbench context column always ships at least the
            # State card when the workspace is rendered. Identifier is the
            # context-column class on the aside.
            self.assertIn(b"studio-os__experience-context", body)

    def test_experience_mode_links_new_scoped_css(self):
        """Guard: studio-experience-mode.css must be linked from the Experience
        mode page so rail-label overflow-wrap and preview-pane styles ship."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("studio_os:experience"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"studio-experience-mode.css", response.content)
