"""
Section 8: Tests for Industry Interoperability views — Caddy ask, discovery, LTI placeholder, frozen page.
"""
import json
from django.test import TestCase, RequestFactory, Client, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolDomain, SchoolMembership
from apps.siteconfig.models import ServiceIntegration


@override_settings(SECURE_SSL_REDIRECT=False)
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

    def test_inactive_school_verified_domain_returns_404(self):
        inactive = School.objects.create(
            name="Inactive School",
            slug="inactive-school",
            subdomain="inactive-school",
            is_active=False,
        )
        SchoolDomain.objects.create(
            school=inactive,
            domain="inactive-school.yoursystem.com",
            kind=SchoolDomain.Kind.SUBDOMAIN,
            is_verified=True,
        )
        from apps.schools.section8_views import verify_caddy_domain
        request = self.factory.get("/api/caddy-check/", {"domain": "inactive-school.yoursystem.com"})
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

    def test_caddy_rate_limit_returns_429_when_exceeded(self):
        from unittest.mock import patch
        from apps.schools.section8_views import verify_caddy_domain
        with patch("apps.schools.section8_views.throttle_ip_request", return_value=(False, 900)):
            request = self.factory.get("/api/caddy-check/", {"domain": "greenwood.yoursystem.com"})
            request.META["REMOTE_ADDR"] = "10.0.0.1"
            response = verify_caddy_domain(request)
        self.assertEqual(response.status_code, 429)


@override_settings(SECURE_SSL_REDIRECT=False)
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


@override_settings(SECURE_SSL_REDIRECT=False)
class SchoolFinderTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="St Marys Academy",
            slug="st-marys-academy",
            subdomain="st-marys-academy",
            is_active=True,
        )

    def test_find_school_page_renders(self):
        response = self.client.get(reverse("find_school"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Access Your Campus", response.content.decode())

    def test_find_school_hx_returns_matching_result(self):
        response = self.client.get(
            reverse("find_school"),
            {"q": "st marys"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode().lower()
        self.assertIn("st marys academy", body)
        self.assertIn("st-marys-academy", body)


@override_settings(SECURE_SSL_REDIRECT=False)
class LtiLaunchRuntimeTests(TestCase):
    """LTI launch endpoints perform OIDC initiation and callback checks."""

    def setUp(self):
        self.client = Client()
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
            endpoint_url="https://lms.example.com/oidc/auth",
            client_id="client-123",
            config={
                "deployment_id": "dep-1",
                "public_jwk": {"kty": "RSA", "kid": "kid-1", "alg": "RS256", "use": "sig", "n": "abc", "e": "AQAB"},
            },
            is_active=True,
        )

    @staticmethod
    def _b64(obj):
        import json
        import base64
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    def _unsigned_id_token(self, *, nonce: str, deployment_id: str = "dep-1"):
        header = {"alg": "none", "typ": "JWT"}
        payload = {
            "sub": "student-1",
            "nonce": nonce,
            "https://purl.imsglobal.org/spec/lti/claim/deployment_id": deployment_id,
        }
        return f"{self._b64(header)}.{self._b64(payload)}."

    def test_valid_tool_id_redirects_to_oidc_provider(self):
        response = self.client.get(reverse("lti_launch", args=[self.integration.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("https://lms.example.com/oidc/auth", response["Location"])
        self.assertIn("client_id=client-123", response["Location"])
        self.assertIn("response_type=id_token", response["Location"])

    def test_invalid_tool_id_returns_404(self):
        response = self.client.get(reverse("lti_launch", args=["99999"]))
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.json())

    def test_inactive_tool_returns_404(self):
        self.integration.is_active = False
        self.integration.save()
        response = self.client.get(reverse("lti_launch", args=[self.integration.pk]))
        self.assertEqual(response.status_code, 404)

    def test_misconfigured_tool_returns_400(self):
        self.integration.client_id = ""
        self.integration.save(update_fields=["client_id"])
        response = self.client.get(reverse("lti_launch", args=[self.integration.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("required", response.json())

    def test_callback_with_matching_nonce_returns_200(self):
        init = self.client.get(reverse("lti_launch", args=[self.integration.pk]))
        self.assertEqual(init.status_code, 302)
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(init["Location"])
        state = parse_qs(parsed.query)["state"][0]
        session_key = f"lti_oidc:{self.integration.pk}:{state}"
        nonce = self.client.session[session_key]["nonce"]

        callback = self.client.post(
            reverse("lti_launch_callback", args=[self.integration.pk]),
            data={"state": state, "id_token": self._unsigned_id_token(nonce=nonce)},
        )
        self.assertEqual(callback.status_code, 200)
        self.assertEqual(callback.json().get("status"), "ok")

    def test_callback_with_bad_nonce_returns_403(self):
        init = self.client.get(reverse("lti_launch", args=[self.integration.pk]))
        from urllib.parse import parse_qs, urlparse
        state = parse_qs(urlparse(init["Location"]).query)["state"][0]
        callback = self.client.post(
            reverse("lti_launch_callback", args=[self.integration.pk]),
            data={"state": state, "id_token": self._unsigned_id_token(nonce="wrong")},
        )
        self.assertEqual(callback.status_code, 403)

    def test_jwks_returns_configured_keys(self):
        response = self.client.get(reverse("lti_jwks"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("keys", payload)
        self.assertTrue(any(k.get("kid") == "kid-1" for k in payload["keys"]))

    def test_lti_launch_and_jwks_rate_limit_429_when_exceeded(self):
        from unittest.mock import patch
        with patch("apps.schools.section8_views.throttle_ip_request", return_value=(False, 60)):
            launch = self.client.get(reverse("lti_launch", args=[self.integration.pk]))
            callback = self.client.post(
                reverse("lti_launch_callback", args=[self.integration.pk]),
                data={"state": "s", "id_token": "a.b.c"},
            )
            jwks = self.client.get(reverse("lti_jwks"))
        self.assertEqual(launch.status_code, 429)
        self.assertEqual(callback.status_code, 429)
        self.assertEqual(jwks.status_code, 429)
        self.assertEqual(launch["Retry-After"], "60")


@override_settings(SECURE_SSL_REDIRECT=False)
class LtiServicesRuntimeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="LTI Services School",
            slug="lti-services-school",
            subdomain="lti-services-school",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            username="lti-teacher",
            email="lti-teacher@example.com",
            password="x",
            role=User.Role.TEACHER,
        )
        self.student = User.objects.create_user(
            username="lti-student",
            email="lti-student@example.com",
            password="x",
            role=User.Role.STUDENT,
        )
        SchoolMembership.objects.create(
            school=self.school,
            user=self.teacher,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        SchoolMembership.objects.create(
            school=self.school,
            user=self.student,
            role=User.Role.STUDENT,
            is_primary=True,
        )
        self.integration = ServiceIntegration.objects.create(
            school=self.school,
            service_name="Canvas",
            service_type=ServiceIntegration.ServiceType.LTI,
            endpoint_url="https://canvas.example.com/lti/auth",
            client_id="canvas-client",
            client_secret="canvas-secret",
            config={
                "deployment_id": "dep-services",
                "service_bearer_token": "svc-token-1",
            },
            is_active=True,
        )
        self.other_school = School.objects.create(
            name="LTI Other School",
            slug="lti-other-school",
            subdomain="lti-other-school",
            is_active=True,
        )
        self.other_integration = ServiceIntegration.objects.create(
            school=self.other_school,
            service_name="Canvas Other",
            service_type=ServiceIntegration.ServiceType.LTI,
            endpoint_url="https://canvas.example.com/lti/auth",
            client_id="canvas-client-other",
            client_secret="canvas-secret-other",
            config={
                "deployment_id": "dep-services-other",
                "service_bearer_token": "svc-token-other",
            },
            is_active=True,
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": "Bearer svc-token-1"}

    def test_lineitem_create_score_and_results(self):
        create_lineitem = self.client.post(
            reverse("lti_ags_lineitems", args=[self.integration.pk]),
            data=json.dumps({"label": "Quiz 1", "scoreMaximum": 20}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(create_lineitem.status_code, 201)
        lineitem_id = create_lineitem.json()["id"]

        score_resp = self.client.post(
            reverse("lti_ags_scores", args=[self.integration.pk, lineitem_id]),
            data=json.dumps(
                {
                    "userId": str(self.student.pk),
                    "scoreGiven": 18,
                    "scoreMaximum": 20,
                    "comment": "Good job",
                }
            ),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(score_resp.status_code, 201)

        results = self.client.get(
            reverse("lti_ags_results", args=[self.integration.pk, lineitem_id]),
            **self._auth(),
        )
        self.assertEqual(results.status_code, 200)
        payload = results.json()
        self.assertIn("results", payload)
        self.assertTrue(any(r.get("userId") == str(self.student.pk) for r in payload["results"]))

    def test_nrps_memberships_returns_school_scoped_members(self):
        response = self.client.get(
            reverse("lti_nrps_memberships", args=[self.integration.pk]),
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        members = response.json().get("members", [])
        ids = {m.get("user_id") for m in members}
        self.assertIn(str(self.teacher.pk), ids)
        self.assertIn(str(self.student.pk), ids)

    def test_deep_linking_accepts_content_items(self):
        response = self.client.post(
            reverse("lti_deep_linking", args=[self.integration.pk]),
            data=json.dumps(
                {
                    "content_items": [
                        {"type": "ltiResourceLink", "title": "Cell Biology", "url": "https://publisher.example.com/cell-bio"}
                    ]
                }
            ),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(len(payload.get("accepted", [])), 1)

    def test_services_reject_invalid_token(self):
        response = self.client.get(reverse("lti_nrps_memberships", args=[self.integration.pk]))
        self.assertEqual(response.status_code, 403)

    def test_services_reject_cross_tenant_token(self):
        response = self.client.get(
            reverse("lti_nrps_memberships", args=[self.integration.pk]),
            HTTP_AUTHORIZATION="Bearer svc-token-other",
        )
        self.assertEqual(response.status_code, 403)

    def test_lti_service_endpoints_rate_limit_429_when_exceeded(self):
        from unittest.mock import patch

        checks = [
            ("get", reverse("lti_ags_lineitems", args=[self.integration.pk]), None),
            ("get", reverse("lti_ags_lineitem_detail", args=[self.integration.pk, "line-1"]), None),
            ("get", reverse("lti_ags_scores", args=[self.integration.pk, "line-1"]), None),
            ("get", reverse("lti_ags_results", args=[self.integration.pk, "line-1"]), None),
            ("get", reverse("lti_nrps_memberships", args=[self.integration.pk]), None),
            ("post", reverse("lti_deep_linking", args=[self.integration.pk]), {"content_items": []}),
        ]
        with patch("apps.schools.section8_views.throttle_ip_request", return_value=(False, 90)):
            for method, url, payload in checks:
                if method == "post":
                    response = self.client.post(
                        url,
                        data=json.dumps(payload),
                        content_type="application/json",
                        **self._auth(),
                    )
                else:
                    response = self.client.get(url, **self._auth())
                self.assertEqual(response.status_code, 429, msg=url)
                self.assertEqual(response["Retry-After"], "90", msg=url)


@override_settings(SECURE_SSL_REDIRECT=False)
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


@override_settings(SECURE_SSL_REDIRECT=False)
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
