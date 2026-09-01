from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup

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
        # (scripts/portal_css_bundle_manifest.json), so accept either path. The
        # sheet is a {% static %} argument either way, never emitted text, so that
        # half stays a source read.
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
                # The two markers are markup, and reading them proves nothing: a
                # shell whose body sits inside {% comment %} keeps both strings in
                # its bytes and puts neither on the page. Assert per shell, so the
                # check is real for all four and not just the first.
                assert_markup(
                    self, path, "data-rmc-premium-shell", "data-rmc-page-purpose"
                )

    def test_authenticated_shell_exposes_primary_action_slot_and_action_rail(self):
        # "Exposes" is a claim about what reaches the page, and both hooks are
        # plain markup, so both are asked of the engine. The source reads these
        # replace passed over a control plane and a drawer that emitted nothing.
        assert_markup(
            self,
            ROOT / "templates" / "control_plane_base.html",
            "data-rmc-primary-action-slot",
        )
        assert_markup(
            self,
            ROOT / "templates" / "partials" / "cp_context_drawer_shell.html",
            "data-rmc-action-rail",
        )

    def test_page_header_exposes_page_purpose_marker(self):
        header = (
            ROOT / "templates" / "components" / "rmc_os_page_header.html"
        ).read_text(encoding="utf-8")
        self.assertGreaterEqual(header.count("data-rmc-page-purpose"), 2)
