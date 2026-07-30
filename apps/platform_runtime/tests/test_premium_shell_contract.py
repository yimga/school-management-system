from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class PremiumShellContractTests(SimpleTestCase):
    def test_shared_shells_load_premium_os_css_and_markers(self):
        shell_paths = [
            ROOT / "templates" / "marketing" / "base_marketing.html",
            ROOT / "templates" / "base.html",
            ROOT / "templates" / "portal_base.html",
            ROOT / "templates" / "control_plane_base.html",
        ]

        # base / control_plane_base link rmc-premium-os.css directly; portal_base
        # and base_marketing load it via the v4.02.45 deferred CSS bundle
        # (scripts/portal_css_bundle_manifest.json), so accept either path.
        bundle_manifest = (
            ROOT / "scripts" / "portal_css_bundle_manifest.json"
        ).read_text(encoding="utf-8")
        for path in shell_paths:
            with self.subTest(path=path.name):
                html = path.read_text(encoding="utf-8")
                self.assertTrue(
                    "css/rmc-premium-os.css" in html
                    or "rmc-premium-os.css" in bundle_manifest,
                    f"{path.name} must load premium OS css (direct or via bundle)",
                )
                self.assertIn("data-rmc-premium-shell", html)
                self.assertIn("data-rmc-page-purpose", html)

    def test_authenticated_shell_exposes_primary_action_slot_and_action_rail(self):
        control_plane = (ROOT / "templates" / "control_plane_base.html").read_text(
            encoding="utf-8"
        )
        drawer = (
            ROOT / "templates" / "partials" / "cp_context_drawer_shell.html"
        ).read_text(encoding="utf-8")

        self.assertIn("data-rmc-primary-action-slot", control_plane)
        self.assertIn("data-rmc-action-rail", drawer)

    def test_page_header_exposes_page_purpose_marker(self):
        header = (
            ROOT / "templates" / "components" / "rmc_os_page_header.html"
        ).read_text(encoding="utf-8")
        self.assertGreaterEqual(header.count("data-rmc-page-purpose"), 2)
