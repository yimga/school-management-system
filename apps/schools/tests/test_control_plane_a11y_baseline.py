"""
N3 baseline for control-plane templates: extend shared shell (skip link + main landmark live in
control_plane_base / control_plane_skeleton). See RUNMYCAMPUS §2.1.1 and §0.1.5 N3.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ControlPlaneA11yBaselineTests(SimpleTestCase):
    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_operator_policy_uses_control_plane_base(self):
        text = self._read("templates", "schools", "super_operator_policy.html")
        self.assertIn('extends "control_plane_base.html"', text)
        self.assertIn("<h1", text)
        self.assertIn("bridge_manifest_path", text)

    def test_backlog_unlock_center_uses_control_plane_base(self):
        text = self._read("templates", "schools", "super_backlog_unlock_center.html")
        self.assertIn("control_plane_base.html", text)
        self.assertIn('data-page-archetype="operational-workbench"', text)

    def test_platform_operator_hub_uses_control_plane_base(self):
        text = self._read("templates", "schools", "super_platform_operator_hub.html")
        self.assertIn('extends "control_plane_base.html"', text)
        self.assertIn('id="super-primary-heading"', text)
        self.assertIn("Operator surfaces", text)

    def test_control_plane_base_provides_main_landmark(self):
        text = self._read("templates", "control_plane_base.html")
        self.assertIn('id="cp-main-content"', text)
        self.assertIn('role="main"', text)

    def test_platform_operator_hub_css_has_focus_visible_for_tiles(self):
        """N3: keyboard users see focus rings on /super/platform-operator-hub/ tiles."""
        text = self._read("static", "css", "cp_operator_hub.css")
        self.assertIn(".cp-operator-hub .cpoh-tile:focus-visible", text)
        self.assertIn(".cp-operator-hub .cpoh-model-link:focus-visible", text)
        self.assertIn("prefers-reduced-motion", text)
