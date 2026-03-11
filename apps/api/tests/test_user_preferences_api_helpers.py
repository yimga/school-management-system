from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.api.user_preferences_api import ControlPlanePreferencesAPI, PortalPreferencesAPI


class UserPreferencesApiHelperTests(SimpleTestCase):
    def test_portal_preferences_allowed_ids_returns_empty_on_soft_failure(self):
        request = SimpleNamespace()
        api = PortalPreferencesAPI()

        with patch("apps.api.user_preferences_api.get_effective_site_settings", side_effect=AttributeError):
            self.assertEqual(api._allowed_ids(request), set())

    def test_control_plane_preferences_allowed_ids_returns_empty_on_soft_failure(self):
        request = SimpleNamespace()
        api = ControlPlanePreferencesAPI()

        with patch("apps.schools.control_plane_nav.build_control_plane_nav", side_effect=TypeError):
            self.assertEqual(api._allowed_ids(request), set())
