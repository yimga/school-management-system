"""HTTP tests for super dashboard Phase H + operator curated links (batch 33 #406 / #417)."""

import uuid

from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorSuperDashboardLink
from apps.schools.tests.manager_client import login_manager_control_plane

_MANAGER_HOST = "manager.runmycampus.com"
_PASSWORD = "testpass123"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MANAGER_HOST],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class SuperDashboardHttpTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username=f"super_dashboard_http_{uuid.uuid4().hex[:10]}",
            password=_PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST=_MANAGER_HOST)
        login_manager_control_plane(
            self.client,
            self.user,
            password=_PASSWORD,
            host=_MANAGER_HOST,
        )

    def _get_dashboard(self, **kwargs):
        url = reverse("super:dashboard")
        response = self.client.get(url, HTTP_HOST=_MANAGER_HOST, **kwargs)
        self.assertEqual(
            response.status_code,
            200,
            msg=f"redirect={response.get('Location', '')!r}",
        )
        return response

    def test_dashboard_post_redirects_to_get_without_full_render(self):
        url = reverse("super:dashboard") + "?month=2026-05"
        response = self.client.post(url, HTTP_HOST=_MANAGER_HOST, follow=False)
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertNotIn("/authentication/login/", location)
        self.assertIn("month=2026-05", location)

    def test_dashboard_phase_h_skip_link_targets_globe_mission(self):
        response = self._get_dashboard()
        body = response.content.decode("utf-8")
        self.assertIn('href="#rmc-globe-master-lab"', body)
        self.assertIn('id="rmc-globe-master-lab"', body)
        self.assertIn('id="super-dashboard-main"', body)

    def test_dashboard_renders_operator_super_dashboard_curated_links(self):
        PlatformOperatorSuperDashboardLink.objects.create(
            slug=f"batch-33-cc-{uuid.uuid4().hex[:8]}",
            label="Open command center",
            href="/super/command-center/",
            sort_order=0,
        )
        response = self._get_dashboard()
        body = response.content.decode("utf-8")
        self.assertIn("Open command center", body)
        self.assertIn('href="/super/command-center/"', body)
