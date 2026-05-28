"""v4.00.12 — proves the dashboard-layout per-user override cascade works.

Closes the v3.99.24 deferral ("Per-user UserPreference override cascade layer").
The cascade itself was already in place in ``dashboard_views.get_layout_for_page``:

  1. Per-user layout (``DashboardLayout(user=X, page=Y)``)
  2. Role default (``DashboardLayout(user=None, role=R, page=Y, is_default=True)``)
  3. Legacy/empty fallback

But there was no test pinning that behavior. These tests do that, so a
future refactor of the cascade can't silently regress per-user customization.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.siteconfig.dashboard_views import (
    get_layout_for_page,
    load_dashboard_layout_settings,
)
from apps.siteconfig.models_dashboard import DashboardLayout


User = get_user_model()


class DashboardLayoutCascadeTests(TestCase):
    """The cascade walks per-user → role-default → legacy fallback."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cascade_user_v4_00_12",
            email="cascade@example.com",
            password="x",  # noqa: S106 — test fixture
        )
        # Best-effort role assignment — different deploys carry the field on
        # User vs UserProfile. Both are honored by get_user_role().
        for attr in ("role", "user_role"):
            if hasattr(self.user, attr):
                try:
                    setattr(self.user, attr, "MANAGER")
                    self.user.save(update_fields=[attr])
                    break
                except Exception:  # noqa: BLE001
                    continue

    def test_role_default_visible_when_no_user_override(self):
        DashboardLayout.objects.create(
            user=None,
            role="MANAGER",
            page="backend",
            is_default=True,
            layout={"__settings__": {"requested_widget_ids": ["w-alpha", "w-beta"]}},
        )
        layout_obj = get_layout_for_page(self.user, "backend")
        self.assertIsNotNone(layout_obj, "cascade must fall through to role default")
        self.assertIsNone(layout_obj.user, "fallback row should be unowned")
        settings = load_dashboard_layout_settings(self.user, "backend")
        self.assertEqual(settings.get("requested_widget_ids"), ["w-alpha", "w-beta"])

    def test_per_user_layout_wins_over_role_default(self):
        DashboardLayout.objects.create(
            user=None,
            role="MANAGER",
            page="backend",
            is_default=True,
            layout={"__settings__": {"requested_widget_ids": ["w-role-default"]}},
        )
        DashboardLayout.objects.create(
            user=self.user,
            page="backend",
            layout={"__settings__": {"requested_widget_ids": ["w-user-override"]}},
        )
        layout_obj = get_layout_for_page(self.user, "backend")
        self.assertIsNotNone(layout_obj)
        self.assertEqual(layout_obj.user, self.user, "per-user override must win")
        settings = load_dashboard_layout_settings(self.user, "backend")
        self.assertEqual(settings.get("requested_widget_ids"), ["w-user-override"])

    def test_anonymous_user_returns_none(self):
        from django.contrib.auth.models import AnonymousUser
        result = get_layout_for_page(AnonymousUser(), "backend")
        self.assertIsNone(result, "unauthenticated user must NOT resolve a layout")
