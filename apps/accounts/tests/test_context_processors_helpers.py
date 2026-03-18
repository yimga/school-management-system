from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError
from django.test import RequestFactory, TestCase

from apps.accounts.context_processors import dashboard_context, site_settings_context
from apps.accounts.models import User


class AccountsContextProcessorsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="ctx-user",
            password="testpass123",
            role=User.Role.PARENT,
        )

    def test_dashboard_context_tolerates_tenant_prefix_and_notification_failures(self):
        request = self.factory.get("/")
        request.user = self.user

        with (
            patch(
                "apps.schools.tenant_url.get_tenant_prefix",
                side_effect=RuntimeError("tenant prefix unavailable"),
            ),
            patch(
                "apps.finance.models.Notification.objects.filter",
                side_effect=DatabaseError("finance notifications unavailable"),
            ),
            patch(
                "apps.communication.models.Message.objects.filter",
                side_effect=DatabaseError("messages unavailable"),
            ),
        ):
            context = dashboard_context(request)

        self.assertEqual(context["tenant_path_prefix"], "")
        self.assertEqual(context["notifications_unread"], 0)
        self.assertEqual(context["messages_unread_count"], 0)

    def test_dashboard_context_for_anonymous_user_returns_base_context(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()

        context = dashboard_context(request)

        self.assertIn("current_time", context)
        self.assertEqual(context["tenant_path_prefix"], "")
        self.assertFalse(context["simple_mode"])

    def test_site_settings_context_returns_safe_empty_payload_on_db_failure(self):
        request = self.factory.get("/")
        request.user = self.user

        with patch(
            "apps.accounts.context_processors.get_effective_site_settings",
            side_effect=DatabaseError("settings unavailable"),
        ):
            context = site_settings_context(request)

        self.assertEqual(context["SITE"], None)
        self.assertEqual(context["SITE_THEME"], {})
