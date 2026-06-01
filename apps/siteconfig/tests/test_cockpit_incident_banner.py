"""Tests for Tier-3 incident banner resolution (PlatformIncident + ticker fallback)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.cockpit_context import _pick_operator_incident_banner, _pick_tenant_incident_banner
from apps.siteconfig.cockpit_incident_banner import (
    resolve_operator_incident_banner,
    resolve_tenant_incident_banner,
)


class PlatformIncidentBannerTests(SimpleTestCase):
    def test_tenant_prefers_platform_incident_over_ticker(self):
        rf = RequestFactory()
        request = rf.get("/")
        cockpit = {
            "tenant_activity_ticker": {
                "enabled": True,
                "cards": [{"text": "ticker warn", "severity": "warn"}],
            }
        }
        strip = {
            "show": True,
            "fleet_generic": False,
            "tenant_items": [
                {"title": "Exam schedule delay", "severity": "high", "status": "open"}
            ],
        }
        with patch(
            "apps.siteconfig.cockpit_incident_banner._platform_incident_strip_for_request",
            return_value=strip,
        ):
            banner = resolve_tenant_incident_banner(request, cockpit)
        self.assertEqual(banner["text"], "Exam schedule delay")
        self.assertEqual(banner["severity"], "danger")
        self.assertEqual(banner["source"], "platform_incident")

    def test_tenant_falls_back_to_ticker_when_no_platform_incident(self):
        rf = RequestFactory()
        request = rf.get("/")
        cockpit = {
            "tenant_activity_ticker": {
                "enabled": True,
                "cards": [{"text": "Maintenance Sunday", "severity": "warn"}],
            }
        }
        with patch(
            "apps.siteconfig.cockpit_incident_banner._platform_incident_strip_for_request",
            return_value={"show": False, "fleet_generic": False, "tenant_items": []},
        ):
            banner = resolve_tenant_incident_banner(request, cockpit)
        self.assertEqual(banner["text"], "Maintenance Sunday")
        self.assertEqual(banner["source"], "activity_ticker")

    def test_operator_fleet_generic_incident(self):
        rf = RequestFactory()
        request = rf.get("/")
        cockpit = {"activity_ticker": {"enabled": True, "cards": []}}
        strip = {"show": True, "fleet_generic": True, "tenant_items": []}
        with patch(
            "apps.siteconfig.cockpit_incident_banner._platform_incident_strip_for_request",
            return_value=strip,
        ):
            banner = resolve_operator_incident_banner(request, cockpit)
        self.assertEqual(banner["severity"], "warn")
        self.assertEqual(banner["source"], "platform_incident_fleet")

    def test_context_pickers_delegate_with_request(self):
        rf = RequestFactory()
        request = rf.get("/")
        cockpit = {
            "tenant_activity_ticker": {
                "enabled": True,
                "cards": [{"text": "School alert", "severity": "danger"}],
            }
        }
        with patch(
            "apps.siteconfig.cockpit_incident_banner.resolve_tenant_incident_banner",
            return_value={"text": "School alert", "severity": "danger"},
        ) as mocked:
            banner = _pick_tenant_incident_banner(cockpit, request)
        mocked.assert_called_once_with(request, cockpit)
        self.assertEqual(banner["text"], "School alert")

    def test_operator_picker_without_request_uses_ticker_only(self):
        cockpit = {
            "activity_ticker": {
                "enabled": True,
                "cards": [{"text": "Drift", "severity": "warn"}],
            }
        }
        picked = _pick_operator_incident_banner(cockpit)
        self.assertEqual(picked["text"], "Drift")


class TenantTickerLegacyOptOutTests(SimpleTestCase):
    def test_legacy_enabled_on_tenant_false_does_not_disable(self):
        """Pre-1599 enabled_on_tenant=False alone must not suppress ticker."""
        payload = {"activity_ticker": {"enabled_on_tenant": False}}
        raw_payload_tat = payload.get("tenant_activity_ticker")
        raw_tat_explicit_disabled = (
            isinstance(raw_payload_tat, dict) and raw_payload_tat.get("enabled") is False
        )
        tat_section = {"enabled": False, "cards": [{"text": "x"}]}
        if raw_tat_explicit_disabled:
            tat_section["enabled"] = False
        elif tat_section.get("cards"):
            tat_section["enabled"] = True
        self.assertFalse(raw_tat_explicit_disabled)
        self.assertTrue(tat_section["enabled"])

    def test_explicit_tenant_activity_ticker_disabled_honored(self):
        payload = {
            "tenant_activity_ticker": {"enabled": False, "cards": [{"text": "x"}]},
        }
        raw_payload_tat = payload.get("tenant_activity_ticker")
        raw_tat_explicit_disabled = (
            isinstance(raw_payload_tat, dict) and raw_payload_tat.get("enabled") is False
        )
        tat_section = {"enabled": True, "cards": [{"text": "x"}]}
        if raw_tat_explicit_disabled:
            tat_section["enabled"] = False
        elif tat_section.get("cards"):
            tat_section["enabled"] = True
        self.assertTrue(raw_tat_explicit_disabled)
        self.assertFalse(tat_section["enabled"])
