"""Tests for interactive globe marker resolution (Global Footprint)."""
from django.test import SimpleTestCase

from apps.siteconfig.world_map_geo import (
    STATUS_COLORS,
    build_globe_markers,
    build_globe_payload,
)


class WorldMapGeoTests(SimpleTestCase):
    def test_build_globe_markers_uses_settings_location_coords(self):
        rows = [{
            "country_code": "US",
            "is_frozen": False,
            "settings": {
                "location": {
                    "latitude": 34.0522,
                    "longitude": -118.2437,
                    "city": "Los Angeles",
                },
            },
        }]
        markers = build_globe_markers(rows)
        self.assertEqual(len(markers), 1)
        m = markers[0]
        self.assertAlmostEqual(m["lat"], 34.0522, delta=0.5)
        self.assertAlmostEqual(m["lng"], -118.2437, delta=0.5)
        self.assertEqual(m.get("city"), "Los Angeles")

    def test_build_globe_markers_uses_country_centroid(self):
        rows = [{"country_code": "US", "is_frozen": False}]
        markers = build_globe_markers(rows)
        self.assertEqual(len(markers), 1)
        m = markers[0]
        self.assertGreater(m["lat"], 39.0)
        self.assertLess(m["lat"], 42.0)
        self.assertGreater(m["lng"], -76.0)
        self.assertLess(m["lng"], -73.0)
        self.assertEqual(m["status"], "active")
        self.assertEqual(m["color"], STATUS_COLORS["active"]["color"])

    def test_suspended_and_frozen_status_colours(self):
        rows = [
            {"country_code": "GB", "is_active": False, "is_frozen": False},
            {"country_code": "FR", "is_frozen": True},
        ]
        markers = build_globe_markers(rows)
        by_status = {m["status"]: m for m in markers}
        self.assertEqual(by_status["suspended"]["color"], STATUS_COLORS["suspended"]["color"])
        self.assertEqual(by_status["frozen"]["color"], STATUS_COLORS["frozen"]["color"])

    def test_unknown_country_skipped_without_crash(self):
        rows = [{"country_code": "", "is_frozen": False}]
        self.assertEqual(build_globe_markers(rows), [])

    def test_globe_payload_includes_theme_and_geo_url(self):
        payload = build_globe_payload([], auto_rotate=False)
        self.assertIn("markers", payload)
        self.assertIn("theme", payload)
        self.assertFalse(payload["auto_rotate"])
        self.assertTrue(str(payload.get("geo_url", "")).endswith("world-countries-110m.json"))
        self.assertIn("region_centroids", payload)
        self.assertIn("api", payload)

    def test_deterministic_jitter_stable(self):
        rows = [
            {"country_code": "NG", "is_frozen": False},
            {"country_code": "NG", "is_frozen": False},
        ]
        a = build_globe_markers(rows)
        b = build_globe_markers(rows)
        self.assertEqual(a, b)
        self.assertNotEqual(a[0]["lat"], a[1]["lat"])
