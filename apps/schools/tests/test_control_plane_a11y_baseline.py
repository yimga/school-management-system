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

    # test_control_plane_base_provides_main_landmark read the SOURCE and
    # measured VACUOUS. A landmark is what assistive tech finds in the DOM,
    # so it is now ControlPlaneMainLandmarkRendersTests below.

    def test_platform_operator_hub_css_has_focus_visible_for_tiles(self):
        """N3: keyboard users see focus rings on /super/platform-operator-hub/ tiles."""
        text = self._read("static", "css", "cp_operator_hub.css")
        self.assertIn(".cp-operator-hub .cpoh-tile:focus-visible", text)
        self.assertIn(".cp-operator-hub .cpoh-model-link:focus-visible", text)
        self.assertIn("prefers-reduced-motion", text)


# --------------------------------------------------------------------------
# Rendered-output replacements (2026-09-01).
#
# scripts/verify_test_asserts_behaviour.py measured the source checks these
# replace as VACUOUS: each still passed with the template it named made to
# render nothing, while every string it asserts stayed in the file's bytes.
#
# They are TestCase, not SimpleTestCase, and that is not an oversight. The
# shells query the database while rendering (a context processor does), so a
# SimpleTestCase raises DatabaseOperationForbidden -- measured, not assumed.
# The consequence is deliberate and worth knowing: the harness only measures
# DB-free tests, so a test fixed this way leaves its scope rather than
# flipping to SOUND inside it.
# --------------------------------------------------------------------------

from django.test import TestCase  # noqa: E402

from apps.siteconfig.tests._shell_render import (  # noqa: E402
    MANAGER_URLCONF,
    render_shell,
)


class ControlPlaneMainLandmarkRendersTests(TestCase):
    def test_the_main_landmark_reaches_the_page(self):
        html = render_shell(
            "control_plane_base.html", urlconf=MANAGER_URLCONF, host_kind="manager"
        )
        self.assertIn('id="cp-main-content"', html)
        self.assertIn('role="main"', html)

    def test_there_is_exactly_one_main_landmark(self):
        """Two <main> elements is its own a11y defect, and source cannot count."""
        html = render_shell(
            "control_plane_base.html", urlconf=MANAGER_URLCONF, host_kind="manager"
        )
        self.assertEqual(html.count('id="cp-main-content"'), 1)
