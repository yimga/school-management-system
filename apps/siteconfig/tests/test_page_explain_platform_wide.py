"""The "About this page" / Flow Thread strip must render on EVERY authenticated
page, not only routes that registered help.

Root cause closed here: ``build_page_explain_context`` previously set
``rmc_page_explain_enabled`` only when a route had a registered help title/body,
workflow tags, or a field manifest — so the strip self-suppressed on most operator
and tenant pages even though it is wired into all shells. These tests lock the
platform-wide contract: enabled for any authenticated request, with a path-derived
fallback title when a route registers nothing, and still absent for anonymous hits.

SimpleTestCase + mocks: the route-help / workflow / manifest resolvers are stubbed
so the test isolates the enable + fallback-title logic (no DB, no registry setup).
"""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

import apps.siteconfig.page_explain as pe
from apps.siteconfig.page_explain import _fallback_page_title, build_page_explain_context


class _AuthedUser:
    is_authenticated = True
    role = "ADMIN"


class _Anon:
    is_authenticated = False


class PageExplainPlatformWideTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    @mock.patch.object(pe, "build_field_manifest", return_value=[])
    @mock.patch.object(pe, "_workflow_context", return_value=(None, []))
    @mock.patch.object(pe, "resolve_route_help", return_value={})
    def test_enabled_with_fallback_title_on_unregistered_page(self, *_):
        req = self.rf.get("/some/unregistered/page/")
        req.user = _AuthedUser()
        ctx = build_page_explain_context(req)
        self.assertTrue(ctx["rmc_page_explain_enabled"])
        # Last meaningful segment, humanised.
        self.assertEqual(ctx["rmc_page_help"]["title"], "Page")

    @mock.patch.object(pe, "build_field_manifest", return_value=[])
    @mock.patch.object(pe, "_workflow_context", return_value=(None, []))
    @mock.patch.object(
        pe, "resolve_route_help", return_value={"title": "Registered Title"}
    )
    def test_registered_title_is_preserved(self, *_):
        req = self.rf.get("/finance/invoices/")
        req.user = _AuthedUser()
        ctx = build_page_explain_context(req)
        self.assertTrue(ctx["rmc_page_explain_enabled"])
        self.assertEqual(ctx["rmc_page_help"]["title"], "Registered Title")

    def test_anonymous_request_gets_no_strip(self):
        req = self.rf.get("/some/page/")
        req.user = _Anon()
        self.assertEqual(build_page_explain_context(req), {})

    def test_fallback_skips_numeric_and_action_segments(self):
        req = self.rf.get("/admin/finance/notification/123/change/")
        self.assertEqual(_fallback_page_title(req), "Notification")

    def test_fallback_root_is_dashboard(self):
        self.assertEqual(_fallback_page_title(self.rf.get("/")), "Dashboard")

    def test_fallback_humanises_hyphenated_segment(self):
        req = self.rf.get("/super/command-center/")
        self.assertEqual(_fallback_page_title(req), "Command Center")
