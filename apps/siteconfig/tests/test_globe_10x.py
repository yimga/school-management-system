"""Tests for globe API + clustering (batch 1653) + labeling parity (batch 1654)."""

from django.contrib.auth import get_user_model

from django.test import Client, TestCase

from django.urls import reverse



from apps.siteconfig.world_map_geo import build_globe_markers, build_globe_payload, cluster_markers, filter_markers





class GlobeGeo10xTests(TestCase):

    def test_build_globe_payload_includes_10x_keys(self):

        payload = build_globe_payload([], layout="hero", tour_enabled=True)

        self.assertEqual(payload["layout"], "hero")

        self.assertTrue(payload["tour_enabled"])

        self.assertIn("region_centroids", payload)

        self.assertIn("region_labels", payload)

        self.assertIn("country_labels", payload)

        self.assertIn("globe_texture_url", payload)

        self.assertIn("label_zoom", payload)

        self.assertIn("region_palette", payload)

        self.assertIn("iso3_region_map", payload)

        self.assertIn("live_refresh", payload)

        self.assertIn("api", payload)

        self.assertIn("live", payload["api"])

        self.assertIn("operator_fleet_stream", payload["api"])

        self.assertIn("features", payload)

        self.assertTrue(payload["features"].get("fleet_pulse"))

        self.assertIn("arcs", payload)



    def test_country_labels_only_for_tenant_countries(self):

        markers = build_globe_markers([

            {"country_code": "US", "is_frozen": False},

            {"country_code": "US", "is_frozen": False, "name": "Second US"},

            {"country_code": "NG", "is_frozen": False},

        ])

        payload = build_globe_payload(markers)

        labels = payload["country_labels"]

        self.assertEqual(len(labels), 2)

        us = next(l for l in labels if l["country_code"] == "US")

        self.assertIn("United States", us["text"])

        self.assertIn("(2)", us["text"])

        self.assertEqual(us["kind"], "country")

    def test_country_labels_include_svg_coords(self):

        markers = build_globe_markers([{"country_code": "NG", "is_frozen": False}])

        payload = build_globe_payload(markers)

        labels = payload["country_labels"]

        self.assertTrue(labels)

        self.assertIn("svg_x", labels[0])

        self.assertIn("svg_y", labels[0])

    def test_enrich_regional_breakdown_includes_label_color(self):

        from apps.siteconfig.world_map_geo import enrich_regional_breakdown

        rows = enrich_regional_breakdown([{"label": "Europe", "count": "5"}])

        self.assertIn("label_color", rows[0])

        self.assertIn("land_color", rows[0])

    def test_markers_include_country_name(self):

        markers = build_globe_markers([{"country_code": "US", "is_frozen": False}])

        self.assertTrue(markers)

        self.assertIn("country_name", markers[0])

        self.assertIn("region", markers[0])



    def test_cluster_markers_collapses_when_zoomed_out(self):

        markers = [

            {"lat": 40.0 + (i % 3) * 0.001, "lng": -74.0, "region": "North America", "status": "active", "color": "#6ee7b7", "ring_color": "#10", "label": "Active"}

            for i in range(20)

        ]

        clustered = cluster_markers(markers, zoom=0.8)

        self.assertLess(len(clustered), len(markers))

        self.assertTrue(any(c.get("is_cluster") for c in clustered))



    def test_filter_markers_by_region(self):

        markers = build_globe_markers([

            {"country_code": "US", "is_frozen": False},

            {"country_code": "NG", "is_frozen": False},

        ])

        filtered = filter_markers(markers, region="West Africa")

        self.assertTrue(all(m["region"] == "West Africa" for m in filtered))





class GlobePreviewDemoParityTests(TestCase):

    def test_enrich_regional_breakdown_adds_svg_anchors(self):
        from apps.siteconfig.world_map_geo import enrich_regional_breakdown

        rows = enrich_regional_breakdown([{"label": "Europe", "count": "5"}])
        self.assertEqual(rows[0]["svg_x"], 214.0)
        self.assertEqual(rows[0]["svg_y"], 92.0)

    def test_cockpit_context_enriches_regional_breakdown(self):
        from apps.siteconfig.cockpit_context import _ensure_world_map_globe_json

        cockpit = {
            "live_world_map": {
                "enabled": True,
                "regional_breakdown": [{"label": "West Africa", "count": "3"}],
                "globe_payload": {"markers": [], "theme": {}},
            }
        }
        _ensure_world_map_globe_json(cockpit)
        rows = cockpit["live_world_map"]["regional_breakdown"]
        self.assertEqual(rows[0]["svg_x"], 244.0)

    def test_world_map_demo_has_labeling_and_svg_anchors(self):

        from apps.siteconfig.cockpit_manager_200x_preview_data import _world_map_demo



        payload = _world_map_demo()

        self.assertTrue(payload.get("globe_payload", {}).get("region_labels"))

        breakdown = payload.get("regional_breakdown") or []

        self.assertTrue(breakdown)

        self.assertIn("svg_x", breakdown[0])

        dots = payload.get("tenant_dots") or []

        self.assertTrue(dots)

        self.assertIn("region", dots[0])

        self.assertIn("location_title", dots[0])





class GlobeAPITests(TestCase):

    def setUp(self):

        User = get_user_model()

        self.staff = User.objects.create_user(

            username="globe-staff",

            password="Test1234!",

            is_staff=True,

            is_superuser=True,

        )

        self.client = Client()



    def test_markers_api_requires_staff(self):

        url = reverse("super:api_globe_markers")

        anon = self.client.get(url)

        self.assertIn(anon.status_code, (302, 403))

        self.client.force_login(self.staff)

        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

        data = resp.json()

        self.assertIn("markers", data)

        self.assertIn("country_labels", data)

        self.assertIn("updated_at", data)



    def test_live_api_returns_full_bundle(self):

        url = reverse("super:api_globe_live")

        self.client.force_login(self.staff)

        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

        data = resp.json()

        self.assertIn("revision", data)

        self.assertIn("markers", data)

        self.assertIn("region_labels", data)

        self.assertIn("regional_breakdown", data)

        self.assertIn("schools_live", data)

        self.assertIn("tour_waypoints", data)

        self.assertIsInstance(data["tour_waypoints"], list)

    def test_live_api_zoom_reclusters(self):

        from apps.siteconfig.world_map_geo import build_globe_markers, build_globe_live_bundle

        markers = build_globe_markers([

            {"country_code": "US", "is_frozen": False},

            {"country_code": "US", "is_frozen": False, "name": "Second US"},

        ])

        wide = build_globe_live_bundle(markers, zoom=0.8)

        tight = build_globe_live_bundle(markers, zoom=2.5)

        self.assertLessEqual(len(wide["markers"]), len(tight["markers"]))

    def test_build_globe_live_bundle_includes_tour_waypoints(self):

        from apps.siteconfig.world_map_geo import build_globe_live_bundle, build_globe_markers

        markers = build_globe_markers([

            {"country_code": "US", "is_frozen": False},

            {"country_code": "NG", "is_frozen": False},

        ])

        bundle = build_globe_live_bundle(markers)

        self.assertIn("tour_waypoints", bundle)

        self.assertTrue(bundle["tour_waypoints"])

    def test_compute_globe_revision_changes_with_status(self):

        from apps.siteconfig.world_map_geo import build_globe_markers, compute_globe_revision

        a = build_globe_markers([{"country_code": "US", "is_frozen": False}])

        b = build_globe_markers([{"country_code": "US", "is_frozen": True}])

        self.assertNotEqual(compute_globe_revision(a), compute_globe_revision(b))

    def test_stream_api_requires_staff(self):

        url = reverse("super:api_globe_stream")

        self.client.force_login(self.staff)

        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

        self.assertTrue(resp.get("Content-Type", "").startswith("text/event-stream"))

