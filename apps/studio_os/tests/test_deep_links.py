"""Studio OS deep links when manager host lacks tenant namespaces."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import NoReverseMatch

from apps.studio_os.deep_links import studio_legacy_urls_map, studio_resolve_url


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

    @override_settings(STUDIO_APPROVAL_HUB_TENANT_BASE_URL="https://tenant.test")
    @patch("apps.studio_os.deep_links.reverse", side_effect=NoReverseMatch())
    def test_legacy_map_uses_tenant_base_when_reverse_missing(self, _mock_rev):
        m = studio_legacy_urls_map()
        self.assertEqual(
            m.get("guided_onboarding"),
            "https://tenant.test/siteconfig/guided-onboarding/",
        )
