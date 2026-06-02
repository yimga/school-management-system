"""Render deploy smoke: manager /super/ shell fragments must render without 500-class template errors."""

from __future__ import annotations

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings


@override_settings(TEMPLATES_DEBUG=True)
class RenderDeployShellSmokeTests(SimpleTestCase):
    def _manager_request(self, path: str = "/super/"):
        rf = RequestFactory()
        request = rf.get(path)
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=True,
            is_staff=True,
            pk=1,
            role="ADMIN",
            username="admin",
            email="admin@test.com",
        )
        request.public_host_kind = "manager"
        request.session = {}
        return request

    def test_workflow_progress_strip_partial_renders(self):
        html = render_to_string(
            "components/rmc_workflow_progress_strip.html",
            {"request": self._manager_request()},
        )
        self.assertIn("data-rmc-wfp-inline", html)

    def test_incident_banner_partial_renders_with_manager_context_keys(self):
        request = self._manager_request()
        html = render_to_string(
            "partials/cockpit/_operator_incident_banner.html",
            {
                "request": request,
                "operator_incident_banner": None,
                "tenant_incident_banner": None,
            },
        )
        self.assertNotIn("data-rmc-operator-incident-banner", html)

    def test_os_status_strip_renders_with_manager_incident_keys(self):
        html = render_to_string(
            "components/rmc_os_status_strip.html",
            {
                "request": self._manager_request(),
                "platform_status_strip": {"show": True, "tenant_items": []},
                "operator_incident_banner": None,
                "tenant_incident_banner": None,
                "rmc_offline_sync_state": {"pending": 0, "failed": 0, "conflicts": 0},
            },
        )
        self.assertIn('data-rmc-os-status-strip="1"', html)

    def test_cockpit_context_exports_incident_keys_on_manager(self):
        from apps.siteconfig.cockpit_context import cockpit_context

        ctx = cockpit_context(self._manager_request())
        self.assertIn("operator_incident_banner", ctx)
        self.assertIn("tenant_incident_banner", ctx)
