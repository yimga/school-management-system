"""Wizard cache telemetry beacon endpoint."""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.setup_studio.views_wizard_cache_telemetry import wizard_cache_telemetry


class WizardCacheTelemetryTests(SimpleTestCase):
    def test_beacon_accepts_post(self):
        request = RequestFactory().post(
            "/api/wizards/telemetry/cache-event/",
            data={"wizard_key": "tenant_onboarding", "event": "cleared"},
        )
        with mock.patch(
            "apps.setup_studio.views_wizard_cache_telemetry.wizard_telemetry.emit_state_cache_event"
        ) as emit:
            response = wizard_cache_telemetry(request)
        self.assertEqual(response.status_code, 204)
        emit.assert_called_once_with("tenant_onboarding", "cleared")
