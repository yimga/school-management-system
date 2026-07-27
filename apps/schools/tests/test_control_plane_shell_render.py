"""1017 + 1020: Runtime HTML proof for control-plane shell (breadcrumb chrome + rmc_shell markers)."""

import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost"])
class ControlPlaneShellRuntimeRenderTests(TestCase):
    """Manager host + platform operator; real super URLs and templates only."""

    def setUp(self):
        self.host = "manager.runmycampus.com"
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.user = User.objects.create_user(
            username="cp_shell_render_op",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        # A bare force_login writes only the default session cookie and no MFA
        # state; the manager host reads MANAGER_SESSION_COOKIE_NAME and an
        # is_superuser operator carries strict baseline MFA, so RequireMFAMiddleware
        # bounces such a request to /authentication/mfa/setup/ (302). The shared
        # helper enrolls a confirmed TOTP device, binds the manager session store,
        # and marks it MFA-verified — the real state of a logged-in operator.
        self.client = login_manager_client(self.user, password="testpass123")

    def tearDown(self):
        self.env.stop()

    def test_workflow_packs_breadcrumb_actions_inside_chrome_partials(self):
        """1017: Child breadcrumb_actions markup appears between shared chrome slots."""
        url = reverse("super:workflow_packs_catalog")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-chrome="breadcrumb-row"', body)
        self.assertIn('data-shell-chrome="breadcrumb-actions-slot"', body)
        self.assertIn("js-return-to-origin", body)
        self.assertIn("Workflow Packs", body)
        row_i = body.find('data-shell-chrome="breadcrumb-row"')
        slot_i = body.find('data-shell-chrome="breadcrumb-actions-slot"')
        action_i = body.find("js-return-to-origin")
        self.assertLess(row_i, slot_i)
        self.assertLess(slot_i, action_i)

    def test_workflow_packs_control_plane_shell_inventory_markers(self):
        """1020: rmc_shell-backed navbar, layout, breadcrumb partials, sidebar/main."""
        url = reverse("super:workflow_packs_catalog")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-shell-title=", body)
        self.assertIn('data-shell-layout="control-plane"', body)
        self.assertIn('data-rmc-layout-token=', body)
        self.assertIn('data-shell-main="control-plane"', body)
        self.assertIn('data-shell-sidebar="', body)
        self.assertIn("data-authenticated-surface=", body)
        self.assertIn('data-shell-chrome="breadcrumb-row"', body)

    def test_blueprints_catalog_breadcrumb_and_shell_markers(self):
        """1026: Second stable CP catalog page — breadcrumbs, actions, layout markers."""
        url = reverse("super:blueprints_catalog")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-chrome="breadcrumb-row"', body)
        self.assertIn('data-shell-chrome="breadcrumb-actions-slot"', body)
        self.assertIn("js-return-to-origin", body)
        self.assertIn("Blueprint Packs", body)
        self.assertIn("data-rmc-shell-title=", body)
        self.assertIn('data-shell-main="control-plane"', body)
        self.assertIn('data-shell-sidebar="', body)
