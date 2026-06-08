"""Integration tests for Global Footprint globe wiring (batch 1645)."""
from __future__ import annotations

import json

from django.test import SimpleTestCase

from apps.siteconfig.cockpit_context import _ensure_world_map_globe_json
from apps.siteconfig.cockpit_manager_200x import _manager_world_map_defaults
from apps.siteconfig.world_map_geo import build_globe_markers


class WorldGlobeWiringTests(SimpleTestCase):
    def test_defaults_include_globe_json_bootstrap(self):
        payload = _manager_world_map_defaults()
        self.assertTrue(payload.get("enabled"))
        self.assertTrue(payload.get("globe_auto_rotate"))
        self.assertIn("globe_payload_json", payload)
        parsed = json.loads(payload["globe_payload_json"])
        self.assertIn("markers", parsed)
        self.assertIn("theme", parsed)
        self.assertTrue(parsed.get("auto_rotate"))

    def test_ensure_globe_json_backfills_empty_enabled_section(self):
        cockpit = {"live_world_map": {"enabled": True, "schools_live": "1"}}
        _ensure_world_map_globe_json(cockpit)
        lwm = cockpit["live_world_map"]
        self.assertIn("globe_payload_json", lwm)
        self.assertIn("globe_payload", lwm)

    def test_ensure_globe_json_syncs_auto_rotate_from_operator_toggle(self):
        cockpit = {
            "live_world_map": {
                "enabled": True,
                "globe_auto_rotate": False,
                "globe_payload_json": json.dumps({"markers": [], "auto_rotate": True}),
            }
        }
        _ensure_world_map_globe_json(cockpit)
        parsed = json.loads(cockpit["live_world_map"]["globe_payload_json"])
        self.assertFalse(parsed["auto_rotate"])

    def test_ensure_globe_json_noop_when_disabled(self):
        cockpit = {"live_world_map": {"enabled": False}}
        _ensure_world_map_globe_json(cockpit)
        self.assertNotIn("globe_payload_json", cockpit["live_world_map"])

    def test_markers_carry_country_code_for_click_through(self):
        rows = [{"country_code": "NG", "is_frozen": False}]
        markers = build_globe_markers(rows)
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["country_code"], "NG")
