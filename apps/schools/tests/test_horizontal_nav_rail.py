"""
Platform horizontal nav rail — fast contract tests (no DB).

Spine active-state logic and template/CSS wiring are validated here so
Windows SQLite full-client tests are not required for audit closeout.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from apps.schools.super_admin_paired_surfaces import (
    _operator_spine_link_is_active,
    build_operator_surface_spine,
)

ROOT = Path(__file__).resolve().parents[3]


class HorizontalNavRailSpineActiveTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _request(self, path: str, url_name: str | None = None):
        req = self.rf.get(path, HTTP_HOST="manager.runmycampus.com")
        if url_name:
            app, name = url_name.split(":", 1)
            match = Mock()
            match.app_name = app
            match.url_name = name
            req.resolver_match = match
        return req

    def test_dashboard_exactly_one_active_spine_link(self):
        spine = build_operator_surface_spine(self._request("/super/"))
        active = [link for link in spine if link.active]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].link_id, "super_dashboard")

    def test_nested_super_list_has_no_active_spine(self):
        spine = build_operator_surface_spine(
            self._request("/super/schools/", "super:schools_list")
        )
        self.assertFalse(any(link.active for link in spine))

    def test_operator_hub_active_only_on_hub_url(self):
        self.assertTrue(
            _operator_spine_link_is_active(
                self._request(
                    "/super/platform-operator-hub/",
                    "super:platform_operator_hub",
                ),
                "super:platform_operator_hub",
            )
        )
        self.assertFalse(
            _operator_spine_link_is_active(self._request("/super/"), "super:platform_operator_hub")
        )

    def test_configuration_center_active_for_configuration_paths(self):
        self.assertTrue(
            _operator_spine_link_is_active(
                self._request("/configuration/domains/", "configuration:center"),
                "configuration:center",
            )
        )


class HorizontalNavRailTemplateContractTests(SimpleTestCase):
    def test_stylesheet_exists(self):
        self.assertTrue((ROOT / "static/css/rmc-horizontal-nav-rail.css").is_file())

    def test_all_major_shells_load_stylesheet(self):
        shells = (
            "templates/control_plane_skeleton.html",
            "templates/portal_base.html",
            "templates/base.html",
            "templates/admin/base_site.html",
        )
        for rel in shells:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("rmc-horizontal-nav-rail.css", text, rel)

    def test_primary_nav_uses_rail_class(self):
        text = (ROOT / "templates/partials/control_plane_primary_nav.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-horizontal-nav-rail", text)
        self.assertNotIn("flex-wrap align-items-center", text)

    def test_workspace_strip_spine_items_marked(self):
        text = (ROOT / "templates/components/rmc_operator_surface_strip.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-operator-workspace-nav__spine-item", text)
        self.assertIn("rmc-horizontal-nav-rail--secondary", text)


class RailProximityRevealContractTests(SimpleTestCase):
    """Rail-mode "proximity reveal": labels collapse to icons at rest and bloom
    on approach. The magnetic enhancer is wired ONLY in rail mode; the CSS
    reveal is driven by a single --reveal custom property so it degrades to a
    hover/focus reveal without JS."""

    _ITEMS = [
        {"id": "home", "url": "/h/", "label": "Home", "glyph": "H", "is_current": True, "icon": ""},
        {"id": "studio", "url": "/s/", "label": "Studio", "glyph": "S", "is_current": False, "icon": ""},
        {"id": "ops", "url": "/o/", "label": "Operations", "glyph": "O", "is_current": False, "icon": ""},
        {"id": "mkt", "url": "/m/", "label": "Marketplace", "glyph": "M", "is_current": False, "icon": ""},
        {"id": "ana", "url": "/a/", "label": "Analytics", "glyph": "A", "is_current": False, "icon": ""},
        {"id": "mig", "url": "/mi/", "label": "Migration", "glyph": "G", "is_current": False, "icon": ""},
    ]

    def _render(self, rail):
        return render_to_string(
            "partials/control_plane_primary_nav.html",
            {
                "PRIMARY_CONTROL_PLANE_NAV": self._ITEMS,
                "MANAGER_PLATFORM_ADMIN_SHELL": False,
                "rail": rail,
                "hide_security": True,
                "csp_nonce": "TESTNONCE",
            },
        )

    def test_rail_mode_wires_proximity_enhancer(self):
        out = self._render(rail=True)
        self.assertIn('data-rmc-proximity-reveal="1"', out)
        self.assertIn("__rmcProximityReveal", out)
        self.assertIn('nonce="TESTNONCE"', out)  # inline enhancer is CSP-safe

    def test_non_rail_mode_has_no_proximity_enhancer(self):
        # The two non-rail include sites already show full labels — they must
        # not gain the hook or the script.
        out = self._render(rail=False)
        self.assertNotIn("data-rmc-proximity-reveal", out)
        self.assertNotIn("__rmcProximityReveal", out)

    def test_reveal_css_is_single_property_driven_with_focus_baseline(self):
        css = (ROOT / "static/css/rmc-cockpit-skin-v8.css").read_text(encoding="utf-8")
        # one --reveal property drives the label width...
        self.assertIn("max-width: calc(var(--reveal)", css)
        # ...and the baseline reveals on keyboard focus so it works without JS.
        self.assertIn(":focus-visible", css)
