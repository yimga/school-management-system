"""
Assert marketing base template does not load app-only stylesheets.
Marketing surface must use only marketing shell and assets (no dashboard-*, design-system-unified, theme-everywhere-dark).
"""

import unittest
from pathlib import Path


# App-only CSS that must NOT appear in marketing base
FORBIDDEN_IN_MARKETING = (
    "design-system-unified.css",
    "dashboard-responsive.css",
    "dashboard-high-contrast.css",
    "dashboard-text-visibility.css",
    "theme-everywhere-dark.css",
)


class MarketingShellTests(unittest.TestCase):
    """Marketing shell must not include app chrome CSS."""

    def test_base_marketing_does_not_load_app_only_css(self):
        """base_marketing.html must not reference design-system-unified, dashboard-*, or theme-everywhere-dark."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "marketing" / "base_marketing.html"
        if not template.is_file():
            self.skipTest("templates/marketing/base_marketing.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        for forbidden in FORBIDDEN_IN_MARKETING:
            self.assertNotIn(
                forbidden,
                text,
                f"Marketing base must not load app-only CSS: {forbidden}",
            )

    def test_marketing_base_schools_does_not_load_app_only_css(self):
        """schools/marketing_base.html extends base_marketing; ensure it doesn't add app-only CSS."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "schools" / "marketing_base.html"
        if not template.is_file():
            self.skipTest("templates/schools/marketing_base.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        for forbidden in FORBIDDEN_IN_MARKETING:
            self.assertNotIn(
                forbidden,
                text,
                f"Marketing base (schools) must not load app-only CSS: {forbidden}",
            )


class ControlPlaneShellTests(unittest.TestCase):
    """Control-plane shell must not load marketing-only assets."""

    def test_control_plane_skeleton_does_not_load_marketing_only_css(self):
        """control_plane_skeleton.html must not reference marketing-shell.css or tokens-marketing.css."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "control_plane_skeleton.html"
        if not template.is_file():
            self.skipTest("templates/control_plane_skeleton.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        self.assertNotIn(
            "marketing-shell.css",
            text,
            "Control plane must not load marketing-shell.css",
        )
        self.assertNotIn(
            "tokens-marketing.css",
            text,
            "Control plane must not load tokens-marketing.css",
        )
