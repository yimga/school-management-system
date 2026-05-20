"""Manager host allowlist + account menu routes (header dropdown regression)."""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from apps.schools.middleware import (
    MANAGER_HOST_ALLOWED_PREFIXES,
    ReservedPublicHostAccessMiddleware,
)


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ManagerHeaderAccountPathTests(SimpleTestCase):
    def test_allowlist_includes_account_and_kb_paths(self):
        for path in (
            "/authentication/documentation/",
            "/authentication/notifications/",
            "/authentication/notifications/preferences/",
            "/authentication/profile/edit/",
            "/kb/",
            "/feedback-loop/",
            "/help-center/",
        ):
            self.assertTrue(
                any(path.startswith(prefix) for prefix in MANAGER_HOST_ALLOWED_PREFIXES),
                msg=f"missing allowlist for {path}",
            )

    def test_reserved_middleware_allows_documentation_and_notifications(self):
        factory = RequestFactory()
        middleware = ReservedPublicHostAccessMiddleware(lambda r: None)
        for path in (
            "/authentication/documentation/",
            "/authentication/notifications/",
        ):
            request = factory.get(path, HTTP_HOST="manager.runmycampus.com")
            request.user = AnonymousUser()
            self.assertIsNone(middleware.process_request(request))

    def test_reserved_middleware_still_blocks_unknown_account_paths(self):
        factory = RequestFactory()
        middleware = ReservedPublicHostAccessMiddleware(lambda r: None)
        request = factory.get("/authentication/messages/", HTTP_HOST="manager.runmycampus.com")
        request.user = AnonymousUser()
        response = middleware.process_request(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_help_redirects_to_help_center(self):
        from config.manager_urls import manager_help

        request = RequestFactory().get("/help/", HTTP_HOST="manager.runmycampus.com")
        response = manager_help(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/help-center", response["Location"])

    def test_allowlist_covers_password_and_mfa_paths(self):
        for path in (
            "/authentication/profile/password/",
            "/authentication/mfa/setup/",
        ):
            self.assertTrue(
                any(path.startswith(prefix) for prefix in MANAGER_HOST_ALLOWED_PREFIXES),
                msg=f"missing allowlist for {path}",
            )


    def test_account_menu_named_routes_resolve(self):
        for name in (
            "accounts:user_documentation",
            "accounts:user_notifications",
            "accounts:user_profile",
            "kb:kb_home",
        ):
            path = reverse(name)
            match = resolve(path)
            self.assertIsNotNone(match.func)

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_feedback_redirects_to_loop(self):
        from config.manager_urls import manager_feedback

        request = RequestFactory().get("/feedback/", HTTP_HOST="manager.runmycampus.com")
        response = manager_feedback(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/feedback-loop", response["Location"])
