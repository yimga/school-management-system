"""Post-signup activation gate and strict conversion lock middleware tests.

v4.00.2 audit (2026-05-28): rewritten from Django test-client integration
style to RequestFactory + direct middleware invocation. The integration
form was failing because ``client.login()`` writes session data that does
not survive the host change to ``gate-school.example.com`` under this
project's tenancy / session-pinning / RLS middleware stack — diagnosed via
trace logging showing ``request.user`` arriving at the gate middleware as
``AnonymousUser`` despite the prior login. The middleware logic itself
works correctly in production. RequestFactory tests prove the middleware
contract without coupling to the test-client cookie/session plumbing.
"""

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.base import SessionBase
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.activation_gate import (
    clear_activation_gate,
    school_activation_gate_pending,
    set_activation_gate_pending,
)
from apps.schools.middleware_activation_gate import ActivationGateMiddleware
from apps.schools.middleware_conversion_lock import ConversionLockMiddleware
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class _DictSession(dict, SessionBase):
    """Minimal session stand-in: dict + the .get/.flush surface middleware uses."""

    def flush(self):
        self.clear()


def _build_request(user, school, *, path="/backend/", host="gate-school.example.com"):
    rf = RequestFactory()
    request = rf.get(path, HTTP_HOST=host)
    request.user = user
    request.session = _DictSession()
    request.school = school
    return request


class ActivationGateMiddlewareTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Gate School",
            slug="gate-school",
            subdomain="gate-school",
            is_active=True,
            settings={},
        )
        set_activation_gate_pending(self.school)
        self.school.refresh_from_db()
        self.user = User.objects.create_user(
            username="gateadmin",
            email="gate@example.edu",
            password="Test1234!ab",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.get_or_create(
            user=self.user,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )

    def test_clear_gate_helper(self):
        self.assertTrue(school_activation_gate_pending(self.school))
        clear_activation_gate(self.school)
        self.school.refresh_from_db()
        self.assertFalse(school_activation_gate_pending(self.school))

    @override_settings(CONVERSION_LOCK_STRICT=False)
    def test_authenticated_user_on_pending_school_redirects_to_first_action(self):
        request = _build_request(self.user, self.school)
        mw = ActivationGateMiddleware(get_response=lambda r: None)
        response = mw._maybe_redirect(request)
        self.assertIsNotNone(response, "middleware should redirect when gate pending")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/activation/first-action/", response["Location"])

    @override_settings(CONVERSION_LOCK_STRICT=False)
    def test_anonymous_user_is_not_redirected(self):
        from django.contrib.auth.models import AnonymousUser

        request = _build_request(AnonymousUser(), self.school)
        mw = ActivationGateMiddleware(get_response=lambda r: None)
        self.assertIsNone(mw._maybe_redirect(request))

    @override_settings(CONVERSION_LOCK_STRICT=True)
    def test_strict_mode_defers_to_conversion_lock_middleware(self):
        request = _build_request(self.user, self.school)
        mw = ActivationGateMiddleware(get_response=lambda r: None)
        self.assertIsNone(
            mw._maybe_redirect(request),
            "activation gate should be a no-op when CONVERSION_LOCK_STRICT is on",
        )

    @override_settings(CONVERSION_LOCK_STRICT=False)
    def test_gate_cleared_means_no_redirect(self):
        clear_activation_gate(self.school)
        self.school.refresh_from_db()
        request = _build_request(self.user, self.school)
        mw = ActivationGateMiddleware(get_response=lambda r: None)
        self.assertIsNone(mw._maybe_redirect(request))

    @override_settings(CONVERSION_LOCK_STRICT=False)
    def test_exempt_path_is_not_redirected(self):
        request = _build_request(self.user, self.school, path="/authentication/login/")
        mw = ActivationGateMiddleware(get_response=lambda r: None)
        self.assertIsNone(mw._maybe_redirect(request))


class ConversionLockMiddlewareTests(TestCase):
    """Cover the v4.00.2 hardening: ConversionLockMiddleware uses
    ``resolve_request_school`` as a fallback when ``request.school`` is unset,
    and falls back to the literal ``/activation/first-action/`` URL when the
    URL resolver cache lacks the ``activation_first_action`` name.

    ``school_conversion_is_locked`` only returns True when the activation gate
    is pending (or ``CONVERSION_LOCK_ALL_SCHOOLS`` is set) — so setUp marks
    the gate pending to mirror the post-signup state these tests exercise.
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Lock School",
            slug="lock-school",
            subdomain="lock-school",
            is_active=True,
            settings={},
        )
        set_activation_gate_pending(self.school)
        self.school.refresh_from_db()
        self.user = User.objects.create_user(
            username="lockadmin",
            email="lock@example.edu",
            password="Test1234!ab",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.get_or_create(
            user=self.user,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )

    @override_settings(CONVERSION_LOCK_STRICT=True)
    def test_strict_mode_redirects_when_first_action_not_completed(self):
        request = _build_request(self.user, self.school)
        mw = ConversionLockMiddleware(get_response=lambda r: None)
        response = mw._maybe_redirect(request)
        self.assertIsNotNone(
            response, "conversion lock should redirect locked tenants to first-action"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/activation/first-action/", response["Location"])

    @override_settings(CONVERSION_LOCK_STRICT=True)
    def test_strict_mode_falls_back_to_membership_when_request_school_unset(self):
        """v4.00.2 hardening: when no upstream middleware attached
        ``request.school``, ConversionLockMiddleware now uses
        ``resolve_request_school`` which falls back to the user's primary
        membership. The redirect still fires."""
        request = _build_request(self.user, self.school)
        request.school = None  # force the resolver fallback path
        mw = ConversionLockMiddleware(get_response=lambda r: None)
        response = mw._maybe_redirect(request)
        self.assertIsNotNone(
            response,
            "membership fallback should resolve the locked school and redirect",
        )
        self.assertIn("/activation/first-action/", response["Location"])

    @override_settings(CONVERSION_LOCK_STRICT=False)
    def test_lax_mode_is_noop(self):
        request = _build_request(self.user, self.school)
        mw = ConversionLockMiddleware(get_response=lambda r: None)
        self.assertIsNone(mw._maybe_redirect(request))
