"""Studio OS deep links when manager host lacks tenant namespaces."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import NoReverseMatch

from apps.studio_os.deep_links import (
    studio_legacy_urls_map,
    studio_resolve_url,
    url_is_cross_origin_request,
)


class StudioDeepLinksTests(TestCase):
    @override_settings(STUDIO_APPROVAL_HUB_TENANT_BASE_URL="https://school.example.org")
    @patch("apps.studio_os.deep_links.reverse", side_effect=NoReverseMatch())
    def test_studio_resolve_uses_tenant_base_for_portal(self, _mock_rev):
        self.assertEqual(
            studio_resolve_url("portal:parent_dashboard"),
            "https://school.example.org/portal/parent/",
        )

    @override_settings(
        STUDIO_APPROVAL_HUB_TENANT_BASE_URL="",
        MANAGER_PLATFORM_BASE_URL="https://manager.example.org",
    )
    @patch("apps.studio_os.deep_links.reverse", side_effect=NoReverseMatch())
    def test_studio_resolve_super_on_manager_base(self, _mock_rev):
        self.assertEqual(
            studio_resolve_url("super:analytics_overview"),
            "https://manager.example.org/super/analytics/",
        )

    def test_legacy_map_non_empty_when_reverse_works(self):
        m = studio_legacy_urls_map()
        self.assertIn("customizer", m)
        self.assertTrue(m["customizer"].startswith("/"))
        self.assertIn("report_library", m)
        self.assertIn("pane=reports", m["report_library"])

    @override_settings(STUDIO_APPROVAL_HUB_TENANT_BASE_URL="https://tenant.test")
    @patch("apps.studio_os.deep_links.reverse", side_effect=NoReverseMatch())
    def test_legacy_map_uses_tenant_base_when_reverse_missing(self, _mock_rev):
        m = studio_legacy_urls_map()
        self.assertEqual(
            m.get("guided_onboarding"),
            "https://tenant.test/siteconfig/guided-onboarding/",
        )

    @override_settings(STUDIO_APPROVAL_HUB_TENANT_BASE_URL="")
    @patch("apps.studio_os.deep_links.reverse", side_effect=NoReverseMatch())
    def test_siteconfig_same_origin_path_when_tenant_base_empty(self, _mock_rev):
        self.assertEqual(
            studio_resolve_url("siteconfig:theme_colors"),
            "/siteconfig/theme-colors/",
        )

    def test_url_is_cross_origin_request(self):
        from django.test import RequestFactory

        rf = RequestFactory()
        req = rf.get("/", HTTP_HOST="testserver")
        self.assertFalse(url_is_cross_origin_request(req, "/siteconfig/foo/"))
        self.assertTrue(
            url_is_cross_origin_request(
                req, "https://manager.example.com/super/billing/"
            )
        )
