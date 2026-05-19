"""Tenant portal chrome resolution (header/footer variants)."""

from django.test import SimpleTestCase

from apps.siteconfig.portal_chrome import resolve_portal_chrome


class PortalChromeResolverTests(SimpleTestCase):
    def test_minimal_layout_uses_minimal_footer(self):
        class _Theme:
            layout = "MINIMAL"

        out = resolve_portal_chrome(site_theme=_Theme())
        self.assertEqual(out["PORTAL_HEADER_VARIANT"], "minimal")
        self.assertEqual(
            out["PORTAL_FOOTER_PARTIAL"], "components/portal_footers/minimal.html"
        )

    def test_dashboard_pack_chrome_override(self):
        class _Pack:
            config_schema = {
                "chrome": {
                    "header_variant": "wide",
                    "footer_partial": "components/footer.html",
                }
            }

        out = resolve_portal_chrome(site_theme=None, dashboard_pack=_Pack())
        self.assertEqual(out["PORTAL_HEADER_VARIANT"], "wide")

    def test_dashboard_template_chrome_override(self):
        class _Template:
            config_schema = {
                "chrome": {
                    "header_variant": "minimal",
                    "footer_partial": "components/portal_footers/minimal.html",
                }
            }

        out = resolve_portal_chrome(site_theme=None, dashboard_template=_Template())
        self.assertEqual(out["PORTAL_HEADER_VARIANT"], "minimal")
        self.assertEqual(
            out["PORTAL_FOOTER_PARTIAL"],
            "components/portal_footers/minimal.html",
        )

    def test_template_wins_over_pack_when_both_set(self):
        class _Pack:
            config_schema = {"chrome": {"header_variant": "wide"}}

        class _Template:
            config_schema = {"chrome": {"header_variant": "minimal"}}

        out = resolve_portal_chrome(
            site_theme=None,
            dashboard_pack=_Pack(),
            dashboard_template=_Template(),
        )
        self.assertEqual(out["PORTAL_HEADER_VARIANT"], "minimal")
