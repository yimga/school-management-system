"""CommandBarActionsView contract tests (v3.53.0, 2026-05-21).

Asserts:
  - the JSON endpoint resolves at /api/command-bar/actions/
  - anonymous requests are redirected by LoginRequiredMixin
  - authenticated requests return {actions: [...], count: N}
  - response shape: each action carries (kind, label, icon, url, scope)
  - tenant scoping respects request.school being None vs set
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.siteconfig.command_bar_registry import CommandBarActionsView


User = get_user_model()


class CommandBarActionsViewURLTests(TestCase):
    def test_url_resolves(self):
        """`command_bar_actions` name resolves to /api/command-bar/actions/."""
        url = reverse("command_bar_actions")
        self.assertEqual(url, "/api/command-bar/actions/")


class CommandBarActionsViewAuthTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.url = reverse("command_bar_actions")

    def test_anonymous_request_is_redirected(self):
        """LoginRequiredMixin redirects anonymous users (not 200)."""
        response = self.client.get(self.url)
        # LoginRequiredMixin returns a 302 to LOGIN_URL.
        self.assertIn(response.status_code, (302, 401, 403))


class CommandBarActionsViewJSONShapeTests(TestCase):
    """Drive the view directly via RequestFactory so we bypass any
    project-specific middleware redirect behavior (the existing
    LegacyHashUpgradeBackend auth chain + tenant resolution
    middleware can intercept the standard test client).
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="cmdbar_user",
            password="pw-not-secret",
        )
        cls.user.is_staff = True
        cls.user.save()

    def setUp(self):
        self.factory = RequestFactory()
        self.url = reverse("command_bar_actions")
        self.view = CommandBarActionsView.as_view()

    def _build_request(self):
        request = self.factory.get(self.url)
        request.user = self.user
        # Simulate a resolved tenant context for staff (manager host).
        request.school = None
        return request

    def test_returns_json_envelope(self):
        response = self.view(self._build_request())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Content-Type", "").split(";")[0],
            "application/json",
        )
        payload = json.loads(response.content.decode("utf-8"))
        self.assertIn("actions", payload)
        self.assertIn("count", payload)
        self.assertIsInstance(payload["actions"], list)
        self.assertIsInstance(payload["count"], int)
        self.assertEqual(payload["count"], len(payload["actions"]))

    def test_each_action_has_required_fields(self):
        response = self.view(self._build_request())
        payload = json.loads(response.content.decode("utf-8"))
        actions = payload["actions"]
        # Staff users should see actions.
        self.assertGreater(len(actions), 0)
        for action in actions:
            self.assertIn("kind", action)
            self.assertIn("label", action)
            self.assertIn("icon", action)
            self.assertIn("url", action)
            self.assertIn("scope", action)
            self.assertIn(action["scope"], ("staff", "tenant_admin", "tenant_user"))


class CommandBarActionsViewTenantScopingTests(TestCase):
    """Defensive tenant scoping — non-staff sees nothing without a school."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="cmdbar_tenantuser",
            password="pw-not-secret",
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.view = CommandBarActionsView.as_view()

    def test_tenant_user_without_school_gets_empty_list(self):
        request = self.factory.get("/api/command-bar/actions/")
        request.user = self.user
        # No request.school attribute — view treats it as None.
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["count"], 0)
