"""Operator policy page — manager host / super."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*"])
class SuperOperatorPolicyViewTests(TestCase):
    def test_operator_policy_200_manager_host(self):
        user = User.objects.create_user(
            username="op_policy_su",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(user, password="x")
        url = reverse("super:operator_policy")
        r = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Operator policy", html=False)
        self.assertContains(r, "bridge-manifest", html=False)

    def test_backlog_unlock_center_200_manager_host(self):
        user = User.objects.create_user(
            username="op_backlog_su",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(user, password="x")
        url = reverse("super:backlog_unlock_center")
        r = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Backlog unlock center", html=False)

    def test_fleet_governed_changes_200_manager_host(self):
        user = User.objects.create_user(
            username="op_fleet_su",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(user, password="x")
        url = reverse("super:fleet_governed_changes")
        r = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Fleet governed changes", html=False)

    @patch("django.core.management.call_command")
    def test_backlog_unlock_refresh_passes_emit_events(self, mock_call_command):
        user = User.objects.create_user(
            username="op_backlog_emit",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(user, password="x")
        url = reverse("super:backlog_unlock_center")
        r = self.client.post(
            url,
            {"profile": "smoke"},
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(r.status_code, 200)
        mock_call_command.assert_called_once()
        args, kwargs = mock_call_command.call_args
        self.assertEqual(args[0], "evaluate_backlog_unlocks")
        self.assertTrue(kwargs.get("update_cache"))
        self.assertTrue(kwargs.get("emit_events"))
        self.assertEqual(kwargs.get("profile"), "smoke")
