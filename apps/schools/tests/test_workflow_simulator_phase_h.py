"""Phase H skip links + operator curated links for workflow simulator (batch 24 #271 / #282)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorWorkflowSimulatorLink
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*"])
class WorkflowSimulatorPhaseHTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="workflow_simulator_phase_h",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        # Manager-host operator page: bind the manager session with confirmed +
        # verified MFA (bare force_login bounces 302 through RequireMFAMiddleware).
        self.client = login_manager_client(self.user, password="testpass123")
        self.host = "manager.runmycampus.com"
        cache.clear()

    def test_workflow_simulator_phase_h_skip_link_targets_main(self):
        url = reverse("super:workflow_simulator")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#workflow-simulator-main"', body)
        self.assertIn('id="workflow-simulator-main"', body)

    def test_workflow_simulator_renders_operator_workflow_simulator_curated_links(self):
        PlatformOperatorWorkflowSimulatorLink.objects.create(
            slug="batch-24-phase-b",
            label="Open Phase B diff",
            href="/super/phase-b-snapshot-diff/",
            sort_order=0,
        )
        url = reverse("super:workflow_simulator")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open Phase B diff", body)
        self.assertIn('href="/super/phase-b-snapshot-diff/"', body)
