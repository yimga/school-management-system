"""
Certification: ensure_demo_environment orchestration (idempotent commands, scoped slug).
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase


class EnsureDemoEnvironmentCommandTests(TestCase):
    def test_requires_school_slug(self):
        with self.assertRaises(CommandError) as cm:
            call_command("ensure_demo_environment")
        self.assertIn("school-slug", str(cm.exception).lower())

    @patch("apps.schools.management.commands.ensure_demo_environment.call_command")
    def test_calls_seed_demo_then_seed_demo_tenant_users_with_same_slug(self, mock_cc):
        call_command("ensure_demo_environment", school_slug="cert-demo-school")
        self.assertEqual(mock_cc.call_count, 2)
        mock_cc.assert_any_call("seed_demo", school="cert-demo-school")
        mock_cc.assert_any_call(
            "seed_demo_tenant_users",
            school_slug="cert-demo-school",
            password="Test1234",
            username_prefix="demo",
        )

    @patch("apps.schools.management.commands.ensure_demo_environment.call_command")
    def test_idempotent_double_invoke_same_calls(self, mock_cc):
        call_command("ensure_demo_environment", school_slug="same-slug")
        call_command("ensure_demo_environment", school_slug="same-slug")
        self.assertEqual(mock_cc.call_count, 4)

    @patch("apps.schools.management.commands.ensure_demo_environment.call_command")
    def test_reset_passed_only_to_seed_demo(self, mock_cc):
        call_command(
            "ensure_demo_environment",
            school_slug="z",
            reset=True,
        )
        mock_cc.assert_any_call("seed_demo", school="z", reset=True)
