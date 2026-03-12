from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.portal.views import _parent_workflow_link, _portal_features_status, _whatsapp_invite_link


class PortalViewHelperTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_parent_workflow_link_returns_none_when_reverse_fails(self):
        with patch("apps.portal.views.reverse", side_effect=RuntimeError("reverse unavailable")):
            link = _parent_workflow_link("Finance", "portal:parent_finance")

        self.assertIsNone(link)

    def test_whatsapp_invite_link_falls_back_to_none_when_integration_lookup_fails(self):
        request = self.factory.get("/")
        request.school = object()

        with patch(
            "apps.siteconfig.integration_registry.resolve_active_integration",
            side_effect=RuntimeError("integration lookup failed"),
        ), patch(
            "apps.portal.views.get_effective_site_settings",
            return_value=type(
                "Site",
                (),
                {
                    "whatsapp_admissions_number": "",
                    "whatsapp_support_number": "",
                },
            )(),
        ):
            link = _whatsapp_invite_link(request)

        self.assertIsNone(link)

    def test_whatsapp_invite_link_uses_owner_scoped_support_contact_settings(self):
        request = self.factory.get("/")
        request.school = object()

        with patch(
            "apps.siteconfig.integration_registry.resolve_active_integration",
            side_effect=RuntimeError("integration lookup failed"),
        ), patch(
            "apps.portal.views.get_effective_site_settings",
            return_value=type(
                "Site",
                (),
                {
                    "get_support_contact_settings": lambda self: {
                        "whatsapp_admissions_number": "+15551234567",
                        "whatsapp_support_number": "",
                    },
                },
            )(),
        ), patch("apps.portal.views.get_site_display_name", return_value="North Star Academy"):
            link = _whatsapp_invite_link(request)

        self.assertIn("wa.me/15551234567", link)

    def test_portal_features_status_prefers_owner_scoped_feature_control_settings(self):
        site = type(
            "Site",
            (),
            {
                "get_feature_control_settings": lambda self: {
                    "portal_features": {
                        "documents": False,
                        "messaging": True,
                        "video": True,
                    }
                }
            },
        )()
        with patch("apps.portal.views.get_effective_site_settings", return_value=site):
            items = _portal_features_status()

        by_key = {item["key"]: item for item in items}
        self.assertFalse(by_key["documents"]["enabled"])
        self.assertTrue(by_key["messaging"]["enabled"])
