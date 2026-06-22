"""The tenant activation / conversion gates must NEVER 302 a background fetch.

Root cause closed here: ConversionLockMiddleware (live in prod, CONVERSION_LOCK_STRICT
defaults on) redirected EVERY non-allowlisted request to /activation/first-action/,
including the page's background fetches (/portal/..., /-/version/, copilot-rail
context, offline enqueue). A fetch() can't follow a 302 to an HTML wizard, so it
failed and the page retried — a redirect storm that starved every data widget and
produced a tall empty void on tenant pages. The gates now redirect ONLY top-level
document navigations.

SimpleTestCase: the helper is pure; the middleware path is exercised with mocked
gate state (no DB).
"""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase, override_settings

import apps.schools.middleware_conversion_lock as mcl
from apps.schools.gate_request_kind import is_document_navigation


class IsDocumentNavigationTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_sec_fetch_dest_document_is_navigation(self):
        req = self.rf.get("/dashboard/", HTTP_SEC_FETCH_DEST="document")
        self.assertTrue(is_document_navigation(req))

    def test_sec_fetch_dest_empty_is_background_fetch(self):
        req = self.rf.get("/portal/copilot/rail/context/", HTTP_SEC_FETCH_DEST="empty")
        self.assertFalse(is_document_navigation(req))

    def test_legacy_xhr_header_is_background_fetch(self):
        req = self.rf.get("/-/version/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertFalse(is_document_navigation(req))

    def test_html_accept_is_navigation(self):
        req = self.rf.get("/dashboard/", HTTP_ACCEPT="text/html,application/xhtml+xml")
        self.assertTrue(is_document_navigation(req))

    def test_json_accept_is_background_fetch(self):
        req = self.rf.get("/portal/api/offline/enqueue/", HTTP_ACCEPT="application/json")
        self.assertFalse(is_document_navigation(req))

    def test_no_signals_biases_to_not_navigation(self):
        # No Sec-Fetch-Dest, no XHR header, no html Accept -> do NOT redirect.
        req = self.rf.get("/something/")
        req.META.pop("HTTP_ACCEPT", None)
        self.assertFalse(is_document_navigation(req))


class _User:
    is_authenticated = True


@override_settings(CONVERSION_LOCK_STRICT=True)
class ConversionLockXhrExemptionTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.mw = mcl.ConversionLockMiddleware(lambda r: "PASSTHROUGH")

    def _req(self, **headers):
        req = self.rf.get("/finance/", **headers)
        req.user = _User()
        req.public_host_kind = "tenant"
        req.session = {}
        return req

    @mock.patch(
        "apps.schools.conversion_lock_state.school_conversion_is_locked",
        return_value=True,
    )
    @mock.patch(
        "apps.schools.conversion_lock_state.school_first_action_completed",
        return_value=False,
    )
    @mock.patch(
        "apps.schools.conversion_lock_paths.path_matches_conversion_allowlist",
        return_value=False,
    )
    @mock.patch(
        "apps.lifecycle.tenant_school_resolve.resolve_request_school",
        return_value=object(),
    )
    def test_background_fetch_passes_through(self, *_):
        req = self._req(HTTP_SEC_FETCH_DEST="empty")
        self.assertEqual(self.mw(req), "PASSTHROUGH")

    @mock.patch(
        "apps.schools.conversion_lock_state.school_conversion_is_locked",
        return_value=True,
    )
    @mock.patch(
        "apps.schools.conversion_lock_state.school_first_action_completed",
        return_value=False,
    )
    @mock.patch(
        "apps.schools.conversion_lock_paths.path_matches_conversion_allowlist",
        return_value=False,
    )
    @mock.patch(
        "apps.lifecycle.tenant_school_resolve.resolve_request_school",
        return_value=object(),
    )
    def test_document_navigation_is_redirected(self, *_):
        req = self._req(HTTP_SEC_FETCH_DEST="document")
        resp = self.mw(req)
        self.assertEqual(getattr(resp, "status_code", None), 302)
