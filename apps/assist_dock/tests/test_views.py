"""v4.00.91 Wave B — assist dock view tests (registry introspect + context)."""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock import default_badges  # noqa: F401 — seed
from apps.assist_dock import default_slots  # noqa: F401 — seed
from apps.assist_dock.quick_actions import (
    QuickAction,
    register_quick_action,
    reset_actions_for_tests,
)
from apps.assist_dock.views import (
    _sanitize_page_path,
    dock_context_view,
    registry_introspect,
)


class SanitizePagePathTests(SimpleTestCase):
    def test_empty(self):
        self.assertEqual(_sanitize_page_path(""), "")

    def test_strips_control_chars(self):
        self.assertEqual(_sanitize_page_path("/foo\x00bar\x7fbaz"), "/foobarbaz")

    def test_truncates_long_path(self):
        result = _sanitize_page_path("/" + "x" * 1000)
        self.assertEqual(len(result), 256)


class RegistryIntrospectTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _staff_request(self):
        req = self.rf.get("/assist-dock/registry.json")
        req.user = mock.Mock(is_authenticated=True, is_staff=True, is_active=True)
        return req

    def test_returns_slots(self):
        # registry_introspect is decorated with @staff_member_required; we
        # call the underlying function via __wrapped__ to bypass the
        # decorator (the wrapper expects RequestFactory request + a real
        # auth backend, which is not set up here).
        view = registry_introspect.__wrapped__
        req = self._staff_request()
        response = view(req)
        payload = json.loads(response.content)
        self.assertIn("slots", payload)
        ids = {s["id"] for s in payload["slots"]}
        # back-to-top is the always-on chip (no requires_feature gate); ai-copilot
        # is feature-gated and only appears with ?include_hidden=1.
        self.assertIn("back-to-top", ids)

    def test_filter_by_surface(self):
        view = registry_introspect.__wrapped__
        req = self.rf.get("/assist-dock/registry.json?surface=portal")
        response = view(req)
        payload = json.loads(response.content)
        self.assertEqual(payload["surface"], "portal")


class DockContextViewTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        reset_actions_for_tests()

    def tearDown(self):
        reset_actions_for_tests()

    def _authed_request(self, path="/assist-dock/context.json", role="TEACHER"):
        req = self.rf.get(path)
        req.public_host_kind = "tenant"
        req.user = mock.Mock(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            active_role=role,
        )
        return req

    def test_anonymous_returns_empty_payload(self):
        view = dock_context_view.__wrapped__
        req = self.rf.get("/assist-dock/context.json")
        req.user = mock.Mock(is_authenticated=False)
        response = view(req)
        payload = json.loads(response.content)
        self.assertEqual(payload["badges"], {})
        self.assertEqual(payload["quick_actions"], [])
        self.assertEqual(payload["role"], "anonymous")

    def test_authed_payload_shape(self):
        view = dock_context_view.__wrapped__
        req = self._authed_request("/portal/dashboard/?page=/portal/dashboard/")
        response = view(req)
        payload = json.loads(response.content)
        for key in ("surface", "role", "page_path", "badges", "quick_actions"):
            self.assertIn(key, payload)
        self.assertEqual(payload["role"], "TEACHER")

    def test_quick_actions_filtered_by_path(self):
        register_quick_action(
            QuickAction(
                id="finance-reconcile",
                label="Reconcile",
                icon="bi-cash",
                href="/finance/reconcile/",
                path_prefixes=("/finance/",),
            )
        )
        register_quick_action(
            QuickAction(
                id="reports-export",
                label="Export",
                icon="bi-download",
                href="/reports/export/",
                path_prefixes=("/reports/",),
            )
        )
        view = dock_context_view.__wrapped__
        req = self._authed_request("/assist-dock/context.json?page=/finance/invoices/")
        response = view(req)
        payload = json.loads(response.content)
        ids = {a["id"] for a in payload["quick_actions"]}
        self.assertIn("finance-reconcile", ids)
        self.assertNotIn("reports-export", ids)

    def test_page_path_too_long_is_truncated(self):
        view = dock_context_view.__wrapped__
        long_path = "/" + "x" * 500
        req = self._authed_request("/assist-dock/context.json?page=" + long_path)
        response = view(req)
        payload = json.loads(response.content)
        self.assertLessEqual(len(payload["page_path"]), 256)
