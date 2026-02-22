"""
Section 8: Tests for Industry Interoperability views — Caddy ask, discovery, LTI placeholder, frozen page.
"""
from django.test import TestCase, RequestFactory, Client
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import ServiceIntegration


class VerifyCaddyDomainTests(TestCase):
    """GET /api/caddy-check/?domain=... returns 200 for allowed domain, 404 otherwise."""

    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Greenwood",
            slug="greenwood",
            subdomain="greenwood",
            is_active=True,
        )

    def test_missing_domain_returns_404(self):
        from apps.schools.section8_views import verify_caddy_domain
        request = self.factory.get("/api/caddy-check/")
        response = verify_caddy_domain(request)
        self.assertEqual(response.status_code, 404)

    def test_localhost_not_allowed(self):
        from apps.schools.section8_views import verify_caddy_domain
        for domain in ("localhost", "127.0.0.1", "::1"):
            request = self.factory.get("/api/caddy-check/", {"domain": domain})
            response = verify_caddy_domain(request)
            self.assertEqual(response.status_code, 404, msg=domain)

    def test_subdomain_match_returns_200(self):
        from apps.schools.section8_views import verify_caddy_domain
        request = self.factory.get("/api/caddy-check/", {"domain": "greenwood.yoursystem.com"})
        response = verify_caddy_domain(request)
        self.assertEqual(response.status_code, 200)

    def test_custom_domain_verified_returns_200(self):
        self.school.custom_domain = "greenwood.edu"
        self.school.custom_domain_verified = True
        self.school.save()
        from apps.schools.section8_views import verify_caddy_domain
        request = self.factory.get("/api/caddy-check/", {"domain": "greenwood.edu"})
        response = verify_caddy_domain(request)
        self.assertEqual(response.status_code, 200)

    def test_custom_domain_unverified_returns_404(self):
        # Use a domain whose subdomain does not match this school (greenwood), so view
        # does not match by subdomain and must rely on custom_domain (verified-only).
        self.school.custom_domain = "other-unverified.edu"
        self.school.custom_domain_verified = False
        self.school.save()
        from apps.schools.section8_views import verify_caddy_domain
        request = self.factory.get("/api/caddy-check/", {"domain": "other-unverified.edu"})
        response = verify_caddy_domain(request)
        self.assertEqual(response.status_code, 404)

    def test_unknown_domain_returns_404(self):
        from apps.schools.section8_views import verify_caddy_domain
        request = self.factory.get("/api/caddy-check/", {"domain": "unknown.example.com"})
        response = verify_caddy_domain(request)
        self.assertEqual(response.status_code, 404)

    def test_caddy_ip_allowlist_403_when_ip_not_allowed(self):
        import os
        from unittest.mock import patch
        from apps.schools.section8_views import verify_caddy_domain
        with patch.dict(os.environ, {"CADDY_CHECK_ALLOWED_IPS": "10.0.0.1,10.0.0.2"}):
            request = self.factory.get("/api/caddy-check/", {"domain": "greenwood.yoursystem.com"})
            request.META["REMOTE_ADDR"] = "192.168.1.1"
            response = verify_caddy_domain(request)
        self.assertEqual(response.status_code, 403)

    def test_caddy_ip_allowlist_200_when_ip_allowed(self):
        import os
        from unittest.mock import patch
        from apps.schools.section8_views import verify_caddy_domain
        with patch.dict(os.environ, {"CADDY_CHECK_ALLOWED_IPS": "10.0.0.1"}):
            request = self.factory.get("/api/caddy-check/", {"domain": "greenwood.yoursystem.com"})
            request.META["REMOTE_ADDR"] = "10.0.0.1"
            response = verify_caddy_domain(request)
        self.assertEqual(response.status_code, 200)


class GlobalLoginDiscoveryTests(TestCase):
    """GET/POST /discover/ — form, redirect to school subdomain or login, or error."""

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Test School",
            slug="test-school",
            subdomain="test-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="member@test.com",
            email="member@test.com",
            password="testpass",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )

    def test_get_returns_form(self):
        response = self.client.get(reverse("global_login_discovery"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"email", response.content.lower())
        self.assertIn("Find your school", (response.content.decode() or ""))

    def test_post_empty_email_shows_error(self):
        response = self.client.post(reverse("global_login_discovery"), {"email": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please enter your email", response.content)

    def test_post_known_email_redirects_to_school_subdomain(self):
        response = self.client.post(
            reverse("global_login_discovery"),
            {"email": "member@test.com"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("test-school", response["Location"])
        self.assertTrue(
            response["Location"].startswith("http://test-server/") is False
            or "test-school" in response["Location"]
        )

    def test_post_unknown_email_shows_error(self):
        response = self.client.post(
            reverse("global_login_discovery"),
            {"email": "nobody@example.com"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No school found", response.content)

    def test_discovery_rate_limit_429_when_exceeded(self):
        from unittest.mock import patch
        from apps.schools import section8_views
        with patch.object(section8_views, "_discovery_rate_limit_exceeded", return_value=True):
            response = self.client.post(
                reverse("global_login_discovery"),
                {"email": "nobody@example.com"},
            )
        self.assertEqual(response.status_code, 429)
        self.assertIn(b"Too many attempts", response.content)


class LtiLaunchPlaceholderTests(TestCase):
    """GET /lti/launch/<tool_id>/ returns 501 for valid LTI tool, 404 for invalid."""

    def setUp(self):
        self.school = School.objects.create(
            name="LTI School",
            slug="lti-school",
            subdomain="lti-school",
            is_active=True,
        )
        self.integration = ServiceIntegration.objects.create(
            school=self.school,
            service_name="Moodle",
            service_type=ServiceIntegration.ServiceType.LTI,
            is_active=True,
        )

    def test_valid_tool_id_returns_501(self):
        from apps.schools.section8_views import lti_launch_placeholder
        factory = RequestFactory()
        request = factory.get(f"/lti/launch/{self.integration.pk}/")
        response = lti_launch_placeholder(request, str(self.integration.pk))
        self.assertEqual(response.status_code, 501)
        import json
        data = json.loads(response.content)
        self.assertIn("message", data)
        self.assertIn("LTI 1.3", data["message"])

    def test_invalid_tool_id_returns_404(self):
        from apps.schools.section8_views import lti_launch_placeholder
        factory = RequestFactory()
        request = factory.get("/lti/launch/99999/")
        response = lti_launch_placeholder(request, "99999")
        self.assertEqual(response.status_code, 404)
        import json
        data = json.loads(response.content)
        self.assertIn("error", data)

    def test_inactive_tool_returns_404(self):
        self.integration.is_active = False
        self.integration.save()
        from apps.schools.section8_views import lti_launch_placeholder
        factory = RequestFactory()
        request = factory.get(f"/lti/launch/{self.integration.pk}/")
        response = lti_launch_placeholder(request, str(self.integration.pk))
        self.assertEqual(response.status_code, 404)


class FrozenAccountViewTests(TestCase):
    """GET /account-frozen/ renders template with frozen_reason."""

    def test_frozen_account_renders(self):
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.contrib.auth.models import AnonymousUser
        from apps.schools.section8_views import frozen_account
        factory = RequestFactory()
        request = factory.get("/account-frozen/")
        request.school = None
        request.user = AnonymousUser()
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        response = frozen_account(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Account on hold", content)
        self.assertIn("storage", content.lower())

    def test_frozen_account_with_school_reason(self):
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.contrib.auth.models import AnonymousUser
        from apps.schools.section8_views import frozen_account
        school = School.objects.create(
            name="Frozen School",
            slug="frozen",
            subdomain="frozen",
            is_active=True,
            is_frozen=True,
            frozen_reason="BILLING",
        )
        factory = RequestFactory()
        request = factory.get("/account-frozen/")
        request.school = school
        request.user = AnonymousUser()
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        response = frozen_account(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("billing", content.lower())


class TenantFreezeMiddlewareTests(TestCase):
    """TenantFreezeMiddleware redirects to account_frozen when school.is_frozen, except exempt paths."""

    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Frozen School",
            slug="frozen",
            subdomain="frozen",
            is_active=True,
            is_frozen=True,
            frozen_reason="STORAGE",
        )

    def test_frozen_school_redirects_to_account_frozen(self):
        from apps.schools.middleware import TenantFreezeMiddleware
        from django.http import HttpResponse
        request = self.factory.get("/portal/")
        request.school = self.school
        request.user = type("User", (), {"is_authenticated": False, "is_staff": False, "is_superuser": False})()
        get_response = lambda r: HttpResponse("ok")
        mw = TenantFreezeMiddleware(get_response)
        response = mw(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("account-frozen", response["Location"])

    def test_exempt_path_not_redirected(self):
        from apps.schools.middleware import TenantFreezeMiddleware
        from django.http import HttpResponse
        request = self.factory.get("/account-frozen/")
        request.school = self.school
        request.user = type("User", (), {"is_authenticated": False, "is_staff": False, "is_superuser": False})()
        get_response = lambda r: HttpResponse("ok")
        mw = TenantFreezeMiddleware(get_response)
        response = mw(request)
        self.assertEqual(response.status_code, 200)

    def test_staff_bypass_no_redirect(self):
        from apps.schools.middleware import TenantFreezeMiddleware
        from django.http import HttpResponse
        request = self.factory.get("/portal/")
        request.school = self.school
        request.user = type("User", (), {"is_authenticated": True, "is_staff": True, "is_superuser": False})()
        get_response = lambda r: HttpResponse("ok")
        mw = TenantFreezeMiddleware(get_response)
        response = mw(request)
        self.assertEqual(response.status_code, 200)
