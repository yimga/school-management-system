"""
Tests for ``apps.accounts.middleware_session_pinning.SessionPinningMiddleware``.

Covers the six required scenarios:

* first request records the pin
* same (IP, UA) on a follow-up passes
* different IP is TOLERATED — pinning is on the device (User-Agent), not the IP,
  because a client IP legitimately rotates (cellular/NAT/IPv6) and flushing on it
  logged mobile users out and re-triggered MFA
* different UA flushes the session and writes a CRITICAL audit
* allowlisted paths skip the check
* disabled-via-setting passes
"""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.middleware_session_pinning import (
    SessionPinningMiddleware,
    _hash_user_agent,
)
from apps.accounts.models import User
from apps.compliance.models_audit import AuditLog


def _ok(_request: HttpRequest) -> HttpResponse:
    return HttpResponse(status=200)


class _FixedSessionMiddleware(SessionMiddleware):
    """Keeps a stable session_key across multiple requests in a single test."""


class SessionPinningMiddlewareTests(TestCase):
    UA_CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"
    UA_FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="pinned-user", password="pass1234"
        )
        self.session_mw = SessionMiddleware(_ok)
        self.middleware = SessionPinningMiddleware(_ok)

    # ----- helpers --------------------------------------------------------

    def _make_request(self, path="/portal/dashboard/", *, ip="1.2.3.4", ua=None, user=None):
        ua = ua if ua is not None else self.UA_CHROME
        request = self.factory.get(path, HTTP_USER_AGENT=ua, REMOTE_ADDR=ip)
        # Initialize a real session
        self.session_mw.process_request(request)
        request.user = user if user is not None else self.user
        return request

    def _make_followup_request(self, prior_session, *, path, ip, ua, user=None):
        """Build a second request that reuses the prior session contents."""
        request = self.factory.get(path, HTTP_USER_AGENT=ua, REMOTE_ADDR=ip)
        self.session_mw.process_request(request)
        # Carry forward the pin keys from the first request's session
        for key, value in prior_session.items():
            request.session[key] = value
        request.user = user if user is not None else self.user
        return request

    # ----- tests ----------------------------------------------------------

    def test_first_request_records_pin(self):
        request = self._make_request()
        self.middleware(request)

        self.assertEqual(request.session["_pin_ip"], "1.2.3.4")
        self.assertEqual(request.session["_pin_ua"], _hash_user_agent(self.UA_CHROME))
        # No audit on first sight
        self.assertFalse(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED).exists()
        )

    def test_same_ip_ua_passes(self):
        first = self._make_request()
        self.middleware(first)

        second = self._make_followup_request(
            first.session, path="/portal/dashboard/", ip="1.2.3.4", ua=self.UA_CHROME
        )
        response = self.middleware(second)

        self.assertEqual(response.status_code, 200)
        # Still authenticated, pin unchanged
        self.assertTrue(second.user.is_authenticated)
        self.assertEqual(second.session["_pin_ip"], "1.2.3.4")
        self.assertEqual(second.session["_pin_ua"], _hash_user_agent(self.UA_CHROME))
        # No audit fired
        self.assertFalse(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED).exists()
        )

    def test_different_ip_is_tolerated(self):
        # An IP change alone (cellular tower handoff, office/CGNAT egress rotation,
        # IPv6 privacy address) must NOT flush the session — that full logout +
        # fresh MFA prompt was the "constantly asked for MFA" bug. Same device (UA)
        # => the session survives, the pin is unchanged, and no audit fires.
        first = self._make_request(ip="1.2.3.4")
        self.middleware(first)

        moved = self._make_followup_request(
            first.session, path="/portal/dashboard/", ip="9.9.9.9", ua=self.UA_CHROME
        )
        response = self.middleware(moved)

        self.assertEqual(response.status_code, 200)
        # Session intact — pin keys preserved (first IP retained as an audit ref).
        self.assertEqual(moved.session["_pin_ip"], "1.2.3.4")
        self.assertEqual(moved.session["_pin_ua"], _hash_user_agent(self.UA_CHROME))
        # No pin-mismatch audit for a mere IP change.
        self.assertFalse(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED).exists()
        )

    def test_different_ua_kills_session(self):
        first = self._make_request(ip="1.2.3.4", ua=self.UA_CHROME)
        self.middleware(first)

        attacker = self._make_followup_request(
            first.session, path="/portal/dashboard/", ip="1.2.3.4", ua=self.UA_FIREFOX
        )
        self.middleware(attacker)

        self.assertNotIn("_pin_ip", attacker.session)
        self.assertNotIn("_pin_ua", attacker.session)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.ACCESS_DENIED,
                sensitivity=AuditLog.Sensitivity.CRITICAL,
                model_name="Session",
            ).exists()
        )

    def test_allowlisted_paths_skip_pinning(self):
        # /static/ — even with an authenticated user, no pin should be set
        request = self._make_request(path="/static/css/portal.css")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_pin_ip", request.session)
        self.assertNotIn("_pin_ua", request.session)

        # /media/ — same
        request = self._make_request(path="/media/uploads/avatar.png")
        self.middleware(request)
        self.assertNotIn("_pin_ip", request.session)

        # /admin/jsi18n/ — same
        request = self._make_request(path="/admin/jsi18n/")
        self.middleware(request)
        self.assertNotIn("_pin_ip", request.session)

    @override_settings(SESSION_PINNING_ENABLED=False)
    def test_disabled_via_setting_passes(self):
        # First request should NOT record a pin when the global gate is off
        first = self._make_request(ip="1.2.3.4", ua=self.UA_CHROME)
        self.middleware(first)
        self.assertNotIn("_pin_ip", first.session)
        self.assertNotIn("_pin_ua", first.session)

        # Even a "mismatch" request goes through cleanly with no audit
        second = self._make_followup_request(
            first.session, path="/portal/dashboard/", ip="9.9.9.9", ua=self.UA_FIREFOX
        )
        response = self.middleware(second)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED).exists()
        )

    def test_anonymous_user_skipped(self):
        request = self.factory.get("/portal/dashboard/", HTTP_USER_AGENT=self.UA_CHROME)
        self.session_mw.process_request(request)
        request.user = AnonymousUser()
        self.middleware(request)
        # No pin on an anonymous request
        self.assertNotIn("_pin_ip", request.session)
        self.assertNotIn("_pin_ua", request.session)
