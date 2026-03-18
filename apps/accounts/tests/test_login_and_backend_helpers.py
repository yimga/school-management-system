from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.views import _get_login_page_language, _get_login_sso_integrations


class LoginAndBackendHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(LANGUAGES=(("en", "English"), ("fr", "French")))
    def test_get_login_page_language_uses_tenant_locale_and_normalizes_language_code(
        self,
    ):
        request = self.factory.get("/authentication/login/")
        request.school = SimpleNamespace()

        with patch(
            "apps.siteconfig.tenant_config.get_tenant_locale",
            return_value={"default_language": "fr-CA"},
        ):
            language = _get_login_page_language(request)

        self.assertEqual(language, "fr")

    def test_get_login_sso_integrations_returns_empty_on_operational_failure(self):
        request = self.factory.get("/authentication/login/")
        request.school = SimpleNamespace()

        with patch(
            "apps.accounts.views.ServiceIntegration.objects.filter",
            side_effect=DatabaseError("db unavailable"),
        ):
            integrations = _get_login_sso_integrations(request)

        self.assertEqual(integrations, [])
