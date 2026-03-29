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


class PortalBaseTenantShellTests(unittest.TestCase):
    """Portal/backend/Studio tenant shell must not load control-plane or marketing-only CSS."""

    def test_portal_base_keeps_tenant_surface_contract(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "portal_base.html"
        if not template.is_file():
            self.skipTest("templates/portal_base.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        self.assertIn('data-surface="tenant"', text)
        for required in (
            "css/design-system-unified.css",
            "css/platform-responsive-touch.css",
        ):
            self.assertIn(
                required,
                text,
                f"portal_base must load tenant app chrome: {required}",
            )
        for forbidden in (
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ):
            self.assertNotIn(
                forbidden,
                text,
                f"portal_base must not load other-surface shell CSS: {forbidden}",
            )


class StudioOsShellTests(unittest.TestCase):
    """Studio OS shell extends portal spine; no control-plane or marketing-only CSS."""

    def test_studio_shell_extends_portal_base_only(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "studio_os" / "shell.html"
        if not template.is_file():
            self.skipTest("templates/studio_os/shell.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        self.assertIn('{% extends "portal_base.html" %}', text)
        for forbidden in (
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ):
            self.assertNotIn(
                forbidden,
                text,
                f"Studio shell must not load other-surface CSS: {forbidden}",
            )

    def test_studio_shell_extrastyle_stays_studio_scoped(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        partial = root / "templates" / "studio_os" / "partials" / "shell_extrastyle.html"
        if not partial.is_file():
            self.skipTest("templates/studio_os/partials/shell_extrastyle.html not found")
        text = partial.read_text(encoding="utf-8", errors="replace")
        for forbidden in (
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ):
            self.assertNotIn(
                forbidden,
                text,
                f"Studio extrastyle must not load other-surface CSS: {forbidden}",
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
