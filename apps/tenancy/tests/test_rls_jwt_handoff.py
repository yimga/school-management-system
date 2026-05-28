"""v4.00.5 — RLS-JWT auth-handoff lifecycle tests.

Covers:
  * Anonymous request -> no cookie set.
  * Authenticated request with school resolved -> cookie minted on response.
  * Authenticated request that already carries a valid cookie -> NOT re-minted.
  * user_logged_out signal -> cookie cleared on response.
  * mint_rls_jwt + _verify_jwt round-trip remains intact (smoke).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings

from apps.tenancy.middleware_rls_jwt import (
    RLSJWTBindingMiddleware,
    _RLS_JWT_COOKIE,
    _verify_jwt,
    clear_rls_jwt_cookie,
    mint_rls_jwt,
)


def _build_request(*, user=None, school=None, cookies=None, meta=None, secure=False):
    req = SimpleNamespace()
    req.META = dict(meta or {})
    req.COOKIES = dict(cookies or {})
    req.user = user
    req.school = school
    req.path = "/dashboard/"
    req.get_host = lambda: "tenant.example.com"
    req.is_secure = lambda: secure
    return req


@override_settings(
    RMC_RLS_JWT_SIGNING_KEY="test-signing-key-32chars-aaaaaaa",
    RMC_RLS_JWT_SIGNING_BACKEND="local-env-key",
    USE_DJANGO_TENANTS=False,
    DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}},
)
class RLSJWTHandoffMintTests(SimpleTestCase):
    def setUp(self):
        from services.rls_jwt_signing import reset_signer_cache

        reset_signer_cache()
        self._captured: dict = {}

        def _fake_get_response(request):
            return HttpResponse("ok")

        self.middleware = RLSJWTBindingMiddleware(_fake_get_response)

    def test_anonymous_request_does_not_mint(self):
        request = _build_request(user=SimpleNamespace(is_authenticated=False))
        # Patch rls_school helpers so the middleware doesn't hit Postgres.
        with mock.patch("apps.tenancy.middleware_rls_jwt.set_rls_school_id"), \
             mock.patch("apps.tenancy.middleware_rls_jwt.reset_rls_school_id"):
            response = self.middleware(request)
        self.assertNotIn(_RLS_JWT_COOKIE, response.cookies)

    def test_authenticated_user_with_school_mints_cookie(self):
        user = SimpleNamespace(is_authenticated=True, pk=42, is_superuser=False, is_staff=False)
        school = SimpleNamespace(id="acme-uuid")
        request = _build_request(user=user, school=school)
        with mock.patch("apps.tenancy.middleware_rls_jwt.set_rls_school_id"), \
             mock.patch("apps.tenancy.middleware_rls_jwt.reset_rls_school_id"):
            response = self.middleware(request)
        self.assertIn(_RLS_JWT_COOKIE, response.cookies)
        morsel = response.cookies[_RLS_JWT_COOKIE]
        # Cookie is HttpOnly + SameSite=Lax + 8h max-age
        self.assertEqual(morsel["samesite"], "Lax")
        self.assertTrue(morsel["httponly"])
        self.assertEqual(int(morsel["max-age"]), 60 * 60 * 8)
        # And the token verifies to the right claims.
        claims = _verify_jwt(morsel.value)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["school_id"], "acme-uuid")
        self.assertEqual(claims["user_id"], "42")

    def test_existing_valid_cookie_not_re_minted(self):
        user = SimpleNamespace(is_authenticated=True, pk=42, is_superuser=False, is_staff=False)
        school = SimpleNamespace(id="acme-uuid")
        existing = mint_rls_jwt(school_id="acme-uuid", user_id=42, role="user")
        request = _build_request(user=user, school=school, cookies={_RLS_JWT_COOKIE: existing})
        with mock.patch("apps.tenancy.middleware_rls_jwt.set_rls_school_id"), \
             mock.patch("apps.tenancy.middleware_rls_jwt.reset_rls_school_id"):
            response = self.middleware(request)
        # Middleware finds the token + binds; should NOT additionally set a cookie.
        self.assertNotIn(_RLS_JWT_COOKIE, response.cookies)

    def test_logout_marker_clears_cookie(self):
        user = SimpleNamespace(is_authenticated=False)
        request = _build_request(user=user)
        request._rls_jwt_clear = True
        response = self.middleware(request)
        # delete_cookie sets the cookie with empty value + expires in the past.
        self.assertIn(_RLS_JWT_COOKIE, response.cookies)
        self.assertEqual(response.cookies[_RLS_JWT_COOKIE].value, "")

    def test_role_resolution_promotes_staff_and_superuser(self):
        from apps.tenancy.middleware_rls_jwt import _resolve_user_role

        self.assertEqual(_resolve_user_role(SimpleNamespace(is_superuser=True, is_staff=True), None), "superuser")
        self.assertEqual(_resolve_user_role(SimpleNamespace(is_superuser=False, is_staff=True), None), "staff")
        self.assertEqual(_resolve_user_role(SimpleNamespace(is_superuser=False, is_staff=False), None), "user")
        self.assertEqual(_resolve_user_role(SimpleNamespace(active_role="teacher"), None), "teacher")

    def test_clear_cookie_helper(self):
        response = HttpResponse("x")
        clear_rls_jwt_cookie(response)
        self.assertIn(_RLS_JWT_COOKIE, response.cookies)
        self.assertEqual(response.cookies[_RLS_JWT_COOKIE].value, "")
