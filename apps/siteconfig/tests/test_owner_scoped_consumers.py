from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.siteconfig.middleware.maintenance_mode import MaintenanceModeMiddleware
from apps.siteconfig.portal_sidebar_items import _backend_flags_for_sidebar


class OwnerScopedConsumerTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_maintenance_middleware_prefers_feature_control_accessor(self):
        request = self.factory.get("/")
        site = type(
            "Site",
            (),
            {
                "get_feature_control_settings": lambda self: {
                    "maintenance_mode": True
                }
            },
        )()

        with patch(
            "apps.siteconfig.middleware.maintenance_mode.get_effective_site_settings",
            return_value=site,
        ), patch("apps.siteconfig.middleware.maintenance_mode.cache.get", return_value=None), patch(
            "apps.siteconfig.middleware.maintenance_mode.cache.set"
        ):
            self.assertTrue(MaintenanceModeMiddleware._is_maintenance_enabled(request))

    def test_sidebar_backend_flags_prefers_owner_scoped_accessor(self):
        request = self.factory.get("/")
        site = type(
            "Site",
            (),
            {
                "get_backend_feature_flags": lambda self: {
                    "enable_cahier_de_texte": True
                }
            },
        )()

        with patch(
            "apps.platform_runtime.helpers.get_effective_flags",
            return_value={},
        ):
            flags = _backend_flags_for_sidebar(request, site)

        self.assertTrue(flags["enable_cahier_de_texte"])
