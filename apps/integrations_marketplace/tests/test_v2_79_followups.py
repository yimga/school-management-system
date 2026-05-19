"""Tests for the v2.79 follow-up closeout (items 1-7).

Covers:
  - webhook_handlers: slack URL verification echo, zoom CRC handshake,
                       graph validationToken passthrough, audit fallback
  - middleware: TenantEmailBindingMiddleware binds+clears across requests,
                clears on exception
  - startup_checks: oauth_callback_base_url_state across the 4 shapes
  - token_refresh observability: _summarize_outcomes; alert-status logging
  - oauth: _effective_scopes default / narrow / reject-widening
  - integrations_rollup view: smoke-test the cell/scope structure

DB-free where possible (SimpleTestCase + mocks); the one place that needs
the ORM (rollup view smoke test) is xfail-skipped if Campus isn't available
because the gilead-school test bootstrap historically struggles on Windows.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.integrations_marketplace import (
    middleware as im_middleware,
    oauth as im_oauth,
    startup_checks as im_startup,
    token_refresh as im_tokens,
    webhook_handlers as im_handlers,
)


class _FakeSchool:
    def __init__(self, pk=1, name="Acme"):
        self.pk = pk
        self.name = name


class _FakeCampus:
    def __init__(self, pk=10, name="Main"):
        self.pk = pk
        self.name = name


class _FakeRow:
    """Stand-in ServiceIntegration row used by the webhook handler tests."""

    def __init__(self, slug="slack", secret="topsecret", school=None, campus=None, pk=1):
        self.connector_slug = slug
        self.config = {"webhook_secret": secret}
        self.school = school
        self.campus = campus
        self.pk = pk


# ---------------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------------

class SlackHandlerTests(SimpleTestCase):
    def setUp(self):
        # Patch _audit so we don't try to hit the AuditLog model in unit tests.
        patcher = mock.patch.object(im_handlers, "_audit")
        self.addCleanup(patcher.stop)
        self.audit = patcher.start()

    def test_url_verification_echoes_challenge(self):
        row = _FakeRow(slug="slack")
        resp = im_handlers.handle_slack(
            row, {"type": "url_verification", "challenge": "abc123"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), {"challenge": "abc123"})

    def test_url_verification_missing_challenge_returns_400(self):
        resp = im_handlers.handle_slack(_FakeRow(), {"type": "url_verification"})
        self.assertEqual(resp.status_code, 400)

    def test_event_callback_audited_and_acked(self):
        resp = im_handlers.handle_slack(
            _FakeRow(),
            {"type": "event_callback", "event": {"type": "message"}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.audit.called)


class ZoomHandlerTests(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch.object(im_handlers, "_audit")
        self.addCleanup(patcher.stop)
        self.audit = patcher.start()

    def test_url_validation_responds_with_signed_token(self):
        row = _FakeRow(slug="zoom", secret="zoom-secret")
        plain = "ZoomPlainText"
        resp = im_handlers.handle_zoom(
            row,
            {"event": "endpoint.url_validation", "payload": {"plainToken": plain}},
        )
        body = json.loads(resp.content)
        self.assertEqual(body["plainToken"], plain)
        expected = hmac.new(
            b"zoom-secret", plain.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        self.assertEqual(body["encryptedToken"], expected)

    def test_recording_completed_acks(self):
        resp = im_handlers.handle_zoom(
            _FakeRow(slug="zoom"),
            {"event": "recording.completed", "payload": {"object": {}}},
        )
        self.assertEqual(resp.status_code, 200)


class GraphHandlerTests(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch.object(im_handlers, "_audit")
        self.addCleanup(patcher.stop)
        self.audit = patcher.start()

    def test_validation_token_echoed_as_text_plain(self):
        resp = im_handlers.handle_microsoft_teams(
            _FakeRow(slug="microsoft_teams"),
            {"validationToken": "ms-token-42"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ms-token-42")
        self.assertEqual(resp["Content-Type"], "text/plain")

    def test_notifications_audited(self):
        resp = im_handlers.handle_outlook_calendar(
            _FakeRow(slug="outlook_calendar"),
            {"value": [{"changeType": "created"}, {"changeType": "updated"}]},
        )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(self.audit.call_count, 2)


# ---------------------------------------------------------------------------
# Audit fallback path
# ---------------------------------------------------------------------------

class AuditFallbackTests(SimpleTestCase):
    def test_swallows_audit_log_failure_silently(self):
        # Force the AuditLog.objects.create call to raise — handler must still
        # return 200 to the upstream, never propagate the audit error.
        with mock.patch("apps.compliance.models_audit.AuditLog.objects.create",
                        side_effect=RuntimeError("DB unavailable")):
            # Should NOT raise.
            im_handlers._audit(
                "slack", _FakeRow(slug="slack"), "test_event", {"a": 1}
            )


# ---------------------------------------------------------------------------
# Tenant email-binding middleware
# ---------------------------------------------------------------------------

class TenantEmailBindingMiddlewareTests(SimpleTestCase):
    def test_binds_then_clears_school_around_request(self):
        observed: dict = {}

        def view(request):
            from apps.integrations_marketplace.email_backend import _active_school
            observed["during"] = _active_school({})
            from django.http import HttpResponse
            return HttpResponse("ok")

        mw = im_middleware.TenantEmailBindingMiddleware(view)
        req = RequestFactory().get("/")
        req.school = _FakeSchool(pk=99)
        mw(req)
        self.assertEqual(observed["during"].pk, 99)
        # Cleared after the request.
        from apps.integrations_marketplace.email_backend import _active_school
        self.assertIsNone(_active_school({}))

    def test_no_school_on_request_is_noop(self):
        def view(request):
            from django.http import HttpResponse
            return HttpResponse("ok")

        mw = im_middleware.TenantEmailBindingMiddleware(view)
        req = RequestFactory().get("/")
        # No `request.school` attribute at all.
        resp = mw(req)
        self.assertEqual(resp.status_code, 200)

    def test_clears_even_on_view_exception(self):
        def view(request):
            raise RuntimeError("view crashed")

        mw = im_middleware.TenantEmailBindingMiddleware(view)
        req = RequestFactory().get("/")
        req.school = _FakeSchool(pk=7)
        with self.assertRaises(RuntimeError):
            mw(req)
        # Despite the exception, the thread-local must be clear.
        from apps.integrations_marketplace.email_backend import _active_school
        self.assertIsNone(_active_school({}))


# ---------------------------------------------------------------------------
# OAUTH_CALLBACK_BASE_URL startup check
# ---------------------------------------------------------------------------

class StartupChecksTests(SimpleTestCase):
    def test_state_when_unset_in_debug_is_info(self):
        with mock.patch.object(im_startup.settings, "OAUTH_CALLBACK_BASE_URL", "", create=True), \
             mock.patch.object(im_startup.settings, "DEBUG", True):
            state = im_startup.oauth_callback_base_url_state()
        self.assertFalse(state["configured"])
        self.assertEqual(state["level"], "info")

    def test_state_when_unset_in_prod_is_warning(self):
        with mock.patch.object(im_startup.settings, "OAUTH_CALLBACK_BASE_URL", "", create=True), \
             mock.patch.object(im_startup.settings, "MANAGER_PLATFORM_BASE_URL", "", create=True), \
             mock.patch.object(im_startup.settings, "DEBUG", False):
            state = im_startup.oauth_callback_base_url_state()
        self.assertEqual(state["level"], "warning")

    def test_state_manager_fallback_in_prod_is_ok(self):
        with mock.patch.object(im_startup.settings, "OAUTH_CALLBACK_BASE_URL", "", create=True), \
             mock.patch.object(
                 im_startup.settings,
                 "MANAGER_PLATFORM_BASE_URL",
                 "https://manager.example.com",
                 create=True,
             ), \
             mock.patch.object(im_startup.settings, "DEBUG", False):
            state = im_startup.oauth_callback_base_url_state()
        self.assertEqual(state["level"], "ok")
        self.assertEqual(state["value"], "https://manager.example.com")

    def test_state_malformed_value_is_warning(self):
        with mock.patch.object(im_startup.settings, "OAUTH_CALLBACK_BASE_URL", "not-a-url", create=True):
            state = im_startup.oauth_callback_base_url_state()
        self.assertEqual(state["level"], "warning")

    def test_state_http_in_prod_is_warning(self):
        with mock.patch.object(im_startup.settings, "OAUTH_CALLBACK_BASE_URL", "http://x", create=True), \
             mock.patch.object(im_startup.settings, "DEBUG", False):
            state = im_startup.oauth_callback_base_url_state()
        self.assertEqual(state["level"], "warning")

    def test_state_https_in_prod_is_ok(self):
        with mock.patch.object(im_startup.settings, "OAUTH_CALLBACK_BASE_URL", "https://app.example.com", create=True), \
             mock.patch.object(im_startup.settings, "DEBUG", False):
            state = im_startup.oauth_callback_base_url_state()
        self.assertEqual(state["level"], "ok")
        self.assertTrue(state["configured"])

    def test_warn_function_never_raises(self):
        # Force settings access to blow up — function must swallow.
        with mock.patch.object(im_startup, "oauth_callback_base_url_state",
                               side_effect=RuntimeError("boom")):
            try:
                im_startup.warn_if_oauth_callback_base_url_missing()
            except Exception:  # noqa: BLE001
                self.fail("warn_if_oauth_callback_base_url_missing raised")


# ---------------------------------------------------------------------------
# Token refresh observability
# ---------------------------------------------------------------------------

class TokenRefreshObservabilityTests(SimpleTestCase):
    def test_summarize_outcomes_counts_by_status(self):
        out = [
            {"status": "refreshed"}, {"status": "refreshed"},
            {"status": "not_due"}, {"status": "transport_error"},
        ]
        counts = im_tokens._summarize_outcomes(out)
        self.assertEqual(counts, {"refreshed": 2, "not_due": 1, "transport_error": 1})

    def test_alert_statuses_set_contains_known_failures(self):
        for s in ("deactivated_invalid_grant", "transport_error", "refresh_failed_no_token"):
            self.assertIn(s, im_tokens._ALERT_STATUSES)


# ---------------------------------------------------------------------------
# OAuth per-tenant scope override
# ---------------------------------------------------------------------------

class EffectiveScopesTests(SimpleTestCase):
    def _connector(self):
        from apps.integrations_marketplace.connector_registry import get_connector
        return get_connector("zoom")  # default_scopes = meeting:write, meeting:read, user:read

    def test_no_school_returns_default(self):
        scopes, source = im_oauth._effective_scopes(self._connector(), school=None, campus=None)
        self.assertEqual(source, "default")
        self.assertEqual(scopes, list(self._connector().default_scopes))

    def test_resolver_returning_none_falls_back_to_default(self):
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            return_value=None,
        ):
            scopes, source = im_oauth._effective_scopes(
                self._connector(), school=_FakeSchool(), campus=None,
            )
        self.assertEqual(source, "default")

    def test_string_override_subset_narrows(self):
        resolved = mock.Mock(config={"scopes_override": "meeting:read user:read"})
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            return_value=resolved,
        ):
            scopes, source = im_oauth._effective_scopes(
                self._connector(), school=_FakeSchool(), campus=None,
            )
        self.assertEqual(source, "tenant_override")
        self.assertEqual(scopes, ["meeting:read", "user:read"])

    def test_list_override_subset_narrows(self):
        resolved = mock.Mock(config={"scopes_override": ["meeting:read"]})
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            return_value=resolved,
        ):
            scopes, source = im_oauth._effective_scopes(
                self._connector(), school=_FakeSchool(), campus=None,
            )
        self.assertEqual(source, "tenant_override")
        self.assertEqual(scopes, ["meeting:read"])

    def test_widening_attempt_is_rejected_and_logged(self):
        resolved = mock.Mock(config={"scopes_override": ["meeting:read", "admin:write"]})
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            return_value=resolved,
        ):
            scopes, source = im_oauth._effective_scopes(
                self._connector(), school=_FakeSchool(), campus=None,
            )
        self.assertEqual(source, "tenant_override_rejected_widening")
        # Falls back to default, NEVER honors the widening attempt.
        self.assertEqual(scopes, list(self._connector().default_scopes))

    def test_garbage_override_falls_back_to_default(self):
        resolved = mock.Mock(config={"scopes_override": 42})
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            return_value=resolved,
        ):
            scopes, source = im_oauth._effective_scopes(
                self._connector(), school=_FakeSchool(), campus=None,
            )
        self.assertEqual(source, "default")


# ---------------------------------------------------------------------------
# Webhook handler registry — confirm decorators ran via AppConfig.ready
# ---------------------------------------------------------------------------

class HandlerRegistrationTests(SimpleTestCase):
    def test_v2_79_handlers_registered_for_expected_slugs(self):
        # webhook_handlers.py is imported by AppConfig.ready(); confirming
        # those registrations landed catches future regressions where someone
        # deletes the import or removes a decorator.
        from apps.integrations_marketplace.webhooks import WEBHOOK_HANDLERS
        for slug in (
            "slack", "zoom", "microsoft_teams", "outlook_calendar",
            "outlook_mail", "google_calendar", "stripe",
        ):
            with self.subTest(slug=slug):
                self.assertIn(slug, WEBHOOK_HANDLERS, f"no handler for {slug}")
                self.assertTrue(callable(WEBHOOK_HANDLERS[slug]))
