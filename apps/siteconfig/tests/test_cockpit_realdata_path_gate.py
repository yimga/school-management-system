"""Cockpit context processor realdata path gating."""

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.siteconfig.cockpit_context import (
    _request_wants_cockpit_realdata,
    cockpit_context,
)


class CockpitRealdataPathGateTest(SimpleTestCase):
    def test_anonymous_request_skips_realdata(self):
        request = RequestFactory().get("/authentication/backend/")
        request.user = AnonymousUser()
        self.assertFalse(_request_wants_cockpit_realdata(request))

    def test_finance_list_skips_realdata(self):
        request = RequestFactory().get("/finance/invoices/")
        request.user = type("U", (), {"is_authenticated": True})()
        self.assertFalse(_request_wants_cockpit_realdata(request))

    def test_backend_dashboard_wants_realdata(self):
        request = RequestFactory().get("/authentication/backend/")
        request.user = type("U", (), {"is_authenticated": True})()
        self.assertTrue(_request_wants_cockpit_realdata(request))

    @override_settings(COCKPIT_CONTEXT_REALDATA_ENABLED=False)
    def test_setting_can_disable_realdata(self):
        request = RequestFactory().get("/authentication/backend/")
        request.user = type("U", (), {"is_authenticated": True})()
        self.assertFalse(_request_wants_cockpit_realdata(request))

    @override_settings(COCKPIT_CONTEXT_REALDATA_ENABLED=True)
    @patch("apps.siteconfig.cockpit_context._pick_tenant_incident_banner", return_value=None)
    def test_tenant_context_still_returns_cockpit_key_off_dashboard(self, _banner):
        request = RequestFactory().get("/finance/invoices/")
        request.user = type("U", (), {"is_authenticated": True})()
        request.public_host_kind = "tenant"
        ctx = cockpit_context(request)
        self.assertIn("cockpit", ctx)
