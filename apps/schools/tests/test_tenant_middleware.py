import os
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import Resolver404, resolve

from apps.schools.middleware import (
    LegacyBaseDomainRedirectMiddleware,
    ReservedPublicHostAccessMiddleware,
    TenantMiddleware,
    TenantSchoolNotFoundMiddleware,
    UrlConfSwitcherMiddleware,
    _bind_pending_school_for_tenant_auth,
)
from apps.schools.models import School, SchoolDomain


@override_settings(ALLOWED_HOSTS=["*"])
class TenantMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Tenant Alpha",
            slug="tenant-alpha",
            subdomain="tenant-alpha",
            is_active=True,
        )
        self.middleware = TenantMiddleware(lambda request: None)

    def _request(self, path: str, host: str):
        request = self.factory.get(path, HTTP_HOST=host)
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request.user = AnonymousUser()
        return request

    def test_sets_school_and_session_for_subdomain_host(self):
        with self.settings(MULTI_TENANT_BASE_DOMAIN="example.com"), patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False
        ):
            request = self._request("/portal/", "tenant-alpha.example.com")
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)
        self.assertEqual(request.session.get("school_id"), str(self.school.id))

    def test_tenant_admin_path_is_not_redirected_to_backend(self):
        with self.settings(MULTI_TENANT_BASE_DOMAIN="example.com"), patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False
        ):
            request = self._request("/admin/", "tenant-alpha.example.com")
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)
        self.assertEqual(request.session.get("school_id"), str(self.school.id))

    def test_clears_stale_session_school_when_no_tenant_resolved(self):
        with self.settings(MULTI_TENANT_BASE_DOMAIN="example.com"), patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False
        ):
            request = self._request("/public/", "example.com")
            request.session["school_id"] = str(self.school.id)
            request.session.save()
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertIsNone(request.school)
        self.assertNotIn("school_id", request.session)

    def test_rewrites_tenant_path_prefix_and_preserves_school_scope(self):
        with self.settings(MULTI_TENANT_BASE_DOMAIN="example.com"), patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False
        ):
            request = self._request(
                "/t/tenant-alpha/authentication/login/", "example.com"
            )
            response = self.middleware.process_request(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://tenant-alpha.example.com/authentication/login/",
        )

    def test_resolves_verified_schooldomain_custom_host(self):
        SchoolDomain.objects.create(
            school=self.school,
            domain="portal.tenant-alpha.edu",
            kind=SchoolDomain.Kind.CUSTOM,
            is_verified=True,
        )
        request = self._request("/portal/", "portal.tenant-alpha.edu")
        response = self.middleware.process_request(request)
        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)

    @override_settings(DEBUG=False)
    def test_unknown_tenant_host_redirects_to_root_school_not_found(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/portal/", "unknown.runmycampus.com")
            response = self.middleware.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://runmycampus.com/school-not-found/?slug=unknown",
        )

    def test_manager_host_honors_session_school_id(self):
        """Platform operators on manager host with a selected tenant keep request.school."""
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/siteconfig/dashboard-configuration/", "manager.runmycampus.com")
            request.session["school_id"] = str(self.school.id)
            request.session.save()
            request.public_host_kind = "manager"
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)

    def test_manager_prefix_host_honors_session_without_host_kind(self):
        """manager.* hosts keep session school even when base-domain env is mismatched."""
        with patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "other-platform.example"},
            clear=False,
        ):
            request = self._request(
                "/siteconfig/dashboard-configuration/",
                "manager.runmycampus.com",
            )
            request.session["school_id"] = str(self.school.id)
            request.session.save()
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)
        self.assertEqual(request.session.get("school_id"), str(self.school.id))

    @override_settings(DEBUG=False)
    def test_tenant_path_fallback_redirects_to_subdomain_in_production(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request(
                "/t/tenant-alpha/authentication/login/", "runmycampus.com"
            )
            response = self.middleware.process_request(request)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://tenant-alpha.runmycampus.com/authentication/login/",
        )


@override_settings(ALLOWED_HOSTS=["*"])
class UrlConfSwitcherMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = UrlConfSwitcherMiddleware(lambda request: None)

    def _request(self, path: str, host: str):
        request = self.factory.get(path, HTTP_HOST=host)
        request.user = AnonymousUser()
        return request

    def test_base_domain_uses_public_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_www_base_domain_uses_public_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "www.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_subdomain_uses_tenant_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "lycee-douala.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.tenant_urls")

    def test_tenant_path_prefix_on_base_domain_uses_public_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request(
                "/t/lycee-douala/authentication/login/", "runmycampus.com"
            )
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_reserved_verify_host_uses_public_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "verify.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_reserved_support_host_uses_public_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "support.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_manager_host_uses_manager_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "manager.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.manager_urls")

    def test_api_host_uses_api_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "api.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.api_urls")

    def test_docs_host_uses_docs_urlconf(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "docs.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.docs_urls")

    def test_tenant_urlconf_does_not_mount_superadmin_routes(self):
        with self.assertRaises(Resolver404):
            resolve("/super/", urlconf="config.tenant_urls")


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False)
class LegacyAndReservedHostMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.legacy = LegacyBaseDomainRedirectMiddleware(lambda request: None)
        self.reserved = ReservedPublicHostAccessMiddleware(lambda request: None)

    def _request(self, path: str, host: str):
        request = self.factory.get(path, HTTP_HOST=host)
        request.user = AnonymousUser()
        return request

    def test_legacy_domain_redirects_to_canonical(self):
        with patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "oldcampus.com",
            },
            clear=False,
        ):
            request = self._request("/find/?q=legacy-campus", "oldcampus.com")
            response = self.legacy.process_request(request)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"], "https://runmycampus.com/find/?q=legacy-campus"
        )

    def test_verify_host_redirects_root_to_verify_hub(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/", "verify.runmycampus.com")
            response = self.reserved.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/verify/")

    def test_base_login_redirects_to_campus_discovery(self):
        """Marketing apex must not render tenant login — hand off to /discover/."""
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/authentication/login/", "runmycampus.com")
            request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"
            response = self.reserved.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/discover/", response["Location"])

    def test_base_manager_auth_path_redirects_to_manager_for_browser(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request("/authentication/backend/", "runmycampus.com")
            request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"
            response = self.reserved.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://manager.runmycampus.com/authentication/backend/",
        )

    def test_render_host_login_redirects_to_discovery(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request(
                "/authentication/login/", "school-management-system-2kzk.onrender.com"
            )
            request.META["HTTP_USER_AGENT"] = "Render/1.0"
            response = self.reserved.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/discover/", response["Location"])

    @override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
    def test_manager_host_allows_authentication_backend_path(self):
        """Manager allowlists /authentication/backend/; ReservedPublic passes through."""
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._request(
                "/authentication/backend/", "manager.runmycampus.com"
            )
            response = self.reserved.process_request(request)
        self.assertIsNone(response)


@override_settings(
    ALLOWED_HOSTS=["*", "runmycampus.com", "pending-tenant.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
)
class PendingTenantAuthBypassTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Pending Tenant",
            slug="pending-tenant",
            subdomain="pending-tenant",
            is_active=False,
        )
        self.not_found_mw = TenantSchoolNotFoundMiddleware(lambda request: None)

    def _request(self, path: str, host: str):
        request = self.factory.get(path, HTTP_HOST=host)
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        return request

    def test_bind_pending_school_on_login_path(self):
        request = self._request(
            "/authentication/login/", "pending-tenant.runmycampus.com"
        )
        bound = _bind_pending_school_for_tenant_auth(request, "pending-tenant")
        self.assertTrue(bound)
        self.assertEqual(request.school.id, self.school.id)
        self.assertTrue(getattr(request, "tenant_provisioning_pending", False))

    def test_not_found_middleware_allows_pending_login(self):
        request = self._request(
            "/authentication/login/", "pending-tenant.runmycampus.com"
        )
        response = self.not_found_mw.process_request(request)
        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)
