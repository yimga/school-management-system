"""Platform surface config SOT tests."""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.platform_surface_config import (
    filter_assist_dock_slots,
    resolve_platform_surface_config,
    resolve_sms_offline_config,
)
from apps.assist_dock.registry import AssistDockSlot, register_slot, unregister_slot


class PlatformUrlCatalogTests(SimpleTestCase):
    @mock.patch("apps.siteconfig.platform_surface_config._effective_flags", return_value={})
    def test_catalog_resolves_core_keys(self, _mock_flags):
        from django.test import RequestFactory

        from apps.siteconfig.platform_surface_config import resolve_api_urls

        req = RequestFactory().get("/portal/")
        urls = resolve_api_urls(req)
        for key in (
            "search",
            "ai_line_interpret",
            "entity_students",
            "permission_snapshot",
            "me_schools",
            "crdt_apply",
            "activities",
            "admin_dashboard",
            "wizard_cache_telemetry",
            "dashboard_layout",
            "dashboard_available_widgets",
        ):
            self.assertIn(key, urls)
        if urls.get("dashboard_layout"):
            self.assertIn("{page}", urls["dashboard_layout"])


class PlatformSurfaceConfigTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    @mock.patch("apps.siteconfig.platform_surface_config.resolve_ai_chrome_config")
    @mock.patch("apps.siteconfig.platform_surface_config.resolve_api_urls")
    @mock.patch("apps.siteconfig.platform_surface_config._effective_flags")
    def test_resolve_includes_urls_and_ai(
        self, mock_flags, mock_urls, mock_ai
    ):
        mock_flags.return_value = {"enable_ai_help_assistant": True}
        mock_urls.return_value = {"search": "/api/search/"}
        mock_ai.return_value = {"features": {"help_assistant": True}}
        req = self.rf.get("/portal/")
        cfg = resolve_platform_surface_config(req)
        self.assertEqual(cfg["urls"]["search"], "/api/search/")
        self.assertIn("ai", cfg)
        self.assertIn("cmdk", cfg)

    @mock.patch("apps.siteconfig.platform_surface_config._hydrate_endpoints")
    @mock.patch("apps.siteconfig.platform_surface_config._effective_flags")
    def test_offline_config_uses_named_hydrate(self, mock_flags, mock_hydrate):
        mock_flags.return_value = {}
        mock_hydrate.return_value = [
            {"url": "/api/entities/students/", "store": "students", "normalizer": "student"}
        ]
        req = self.rf.get("/portal/parent/")
        payload = resolve_sms_offline_config(req, offline_enabled_for_school=True)
        self.assertTrue(payload["parentPortalShell"])
        self.assertEqual(len(payload["hydrateEndpoints"]), 1)
        self.assertFalse(payload["walStreamEnabled"])
        json.loads(json.dumps(payload))

    @mock.patch.dict(
        "os.environ",
        {"RMC_WAL_STREAM_ENABLED": "1", "WEB_SERVER_MODE": "asgi"},
        clear=False,
    )
    @mock.patch("apps.siteconfig.platform_surface_config._hydrate_endpoints", return_value=[])
    @mock.patch("apps.siteconfig.platform_surface_config._effective_flags", return_value={})
    def test_wal_stream_enabled_when_asgi_and_env_set(self, _mock_flags, _mock_hydrate):
        req = self.rf.get("/portal/")
        payload = resolve_sms_offline_config(req, offline_enabled_for_school=True)
        self.assertTrue(payload["walStreamEnabled"])
        self.assertTrue(payload["sseStreamsEnabled"])


class AssistDockFilterTests(SimpleTestCase):
    def test_feature_gate_filters_slot(self):
        slot = AssistDockSlot(
            id="test-gate",
            label="T",
            icon="bi-x",
            requires_feature="enable_ai_help_assistant",
        )
        try:
            register_slot(slot)
            out = filter_assist_dock_slots(
                [slot],
                {"enable_ai_help_assistant": False},
            )
            self.assertEqual(out, [])
            out_on = filter_assist_dock_slots(
                [slot],
                {"enable_ai_help_assistant": True},
            )
            self.assertEqual(len(out_on), 1)
        finally:
            unregister_slot("test-gate")
