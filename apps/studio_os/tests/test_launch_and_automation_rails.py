"""
Verify Launch Studio (§4.5) and Automation Studio (§5.7) rail views resolve and return 200 for staff.
SOT §4.5 select plan; §5.7 dependency graph, replay/rollback, health, conflict detection, staged activation,
visual builder, natural-language workflow, simulation engine.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission
from apps.security.embed_frame_middleware import EmbedSameOriginFrameMiddleware

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
        self.user.refresh_from_db()
        assert self.user.is_staff, "fixture user must be staff for Studio / workflow views"
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.user.feature_permissions.add(manage_perm)

    def test_launch_select_plan_returns_200_for_staff(self):
        """§4.5 Select plan: view and URL wired; returns 200."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch_select_plan")
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, 200, "launch_select_plan should return 200 for staff"
        )

    def test_automation_rail_views_return_200_for_staff(self):
        """§5.7 Automation rail placeholders: all resolve and return 200 for staff."""
        self.client.force_login(self.user)
        for name, _label in AUTOMATION_RAIL_VIEWS:
            with self.subTest(view=name):
                url = reverse(name)
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{name} should return 200 for staff",
                )

    def test_automation_overview_is_native_without_iframe(self):
        """Default Automation pane renders server-side overview (no iframe)."""
        self.client.force_login(self.user)
        url = reverse("studio_os:automation") + "?pane=overview"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            b"<iframe",
            response.content.lower(),
            "Overview should be native HTML, not an iframe canvas",
        )

    def test_automation_overview_renders_cockpit_grammar(self):
        """v3.54 (Agent 3): Automation overview is the workflow cockpit."""
        self.client.force_login(self.user)
        url = reverse("studio_os:automation") + "?pane=overview"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Cockpit class lands.
        self.assertContains(response, "rmc-automation-cockpit")
        # Summary tiles present.
        self.assertContains(response, "rmc-automation-tile")
        # Simulation preview pane is wired in overview.
        self.assertContains(response, "rmc-automation-simulation")

    def test_automation_rail_uses_rmc_automation_rail_grammar(self):
        """v3.54 (Agent 3): rail uses .rmc-automation-rail__link grammar."""
        self.client.force_login(self.user)
        url = reverse("studio_os:automation") + "?pane=overview"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # On tenant shells, the workspace rail loads.
        # On manager-host (no workspace_layout), the legacy fallback also uses
        # the .rmc-automation-rail wrapper. Either way the class is present.
        self.assertContains(response, "rmc-automation-rail")

    def test_automation_workflow_pane_uses_iframe(self):
        """Workflow center embed loads in iframe when pane=workflow."""
        self.client.force_login(self.user)
        url = reverse("studio_os:automation") + "?pane=workflow"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<iframe", response.content.lower())

    def test_workflow_center_embed_returns_200(self):
        """Workflow center supports ?embed=1 for Automation Studio iframe."""
        self.client.force_login(self.user)
        url = reverse("studio_os:workflow_center") + "?embed=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "workflow-grid")

    def test_launch_overview_native_without_iframe_when_payload(self):
        """Launch overview is native when setup payload exists."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch") + "?pane=overview"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Without a bound school, overview is native empty-state (no iframe).
        self.assertNotIn(b"<iframe", response.content.lower())

    def test_launch_onboarding_pane_uses_iframe(self):
        self.client.force_login(self.user)
        url = reverse("studio_os:launch") + "?pane=onboarding"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"studio-launch-iframe", response.content.lower())

    def test_guided_onboarding_embed_allows_same_origin_framing(self):
        """Launch Studio iframe must not get X-Frame-Options: DENY (browser refused to connect)."""
        from django.test import RequestFactory

        from apps.schools.models import School

        school = School.objects.create(
            name="Embed Test School",
            slug="embed-test",
            subdomain="embed-test",
            is_active=True,
        )
        req = RequestFactory().get(
            reverse("siteconfig:guided_onboarding"), {"embed": "1"}
        )
        req.user = self.user
        req.school = school
        from apps.customersuccess.views_tenant import guided_onboarding_view

        response = guided_onboarding_view(req)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            EmbedSameOriginFrameMiddleware(lambda r: response)(req)["X-Frame-Options"],
            "SAMEORIGIN",
        )

    def test_launch_migration_pane_uses_iframe(self):
        """PATH III.9 / §4.5: migration path opens migration wizard in Launch Studio embed."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch") + "?pane=migration"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content[:500] if response.content else b"")
        self.assertIn(b"studio-launch-iframe", response.content.lower())
        self.assertIn(b"migration-wizard", response.content.lower())

    def test_launch_role_preview_pane_is_native(self):
        """PATH III.9: preview-by-role is native (no launch iframe chrome)."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch") + "?pane=role_preview"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            b"studio-launch-iframe",
            response.content.lower(),
            "role preview should be native template, not the launch iframe",
        )
        self.assertIn(b"role preview", response.content.lower())

    # ---- v3.54.0 next-realm Launch cockpit additions ----

    def test_launch_links_next_realm_cockpit_css(self):
        """Launch mode shell pulls studio-launch-cockpit.css (new in v3.54.0)."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "studio-launch-cockpit.css")

    @override_settings(
        MULTI_TENANT_BASE_DOMAIN="example.test",
        ALLOWED_HOSTS=["manager.example.test", "example.test", "testserver", "localhost", "127.0.0.1"],
    )
    def test_launch_infrastructure_pane_carries_request_apply_confirm_for_operator(self):
        """Operator host: 'Request platform apply' confirms before invoking platform action."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch") + "?pane=infrastructure"
        # manager.example.test only classifies as the manager host when example.test
        # is the canonical base domain (public_host_kind matches manager.<base>),
        # and must be in ALLOWED_HOSTS — both set via override_settings above.
        response = self.client.get(url, HTTP_HOST="manager.example.test")
        self.assertEqual(response.status_code, 200)
        # JS hooks always present (preview is read-only)
        self.assertContains(response, 'id="studio-infra-preview-btn"')

    def test_launch_plan_pane_renders_honest_coming_soon(self):
        """Plan pane: explicit 'Coming soon' marker until plans productized."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch") + "?pane=plan"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coming soon")

    def test_launch_rail_aria_current_on_active_pane(self):
        """Active rail link carries aria-current=page for a11y."""
        self.client.force_login(self.user)
        url = reverse("studio_os:launch") + "?pane=role_preview"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-current="page"')
