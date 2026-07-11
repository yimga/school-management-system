"""Tests for the shared platform-superadmin promotion service."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.superadmin_service import (
    apply_superadmin_change,
    compute_superadmin_changes,
)

User = get_user_model()


class SuperadminServiceTests(TestCase):
    def test_promote_sets_all_three_signals(self):
        u = User.objects.create_user(
            username="svc1", email="svc1@example.com", password="x",
            role=User.Role.PARENT,
        )
        self.assertFalse(u.is_superuser)
        changes = apply_superadmin_change(u)
        u.refresh_from_db()
        self.assertTrue(u.is_staff)
        self.assertTrue(u.is_superuser)
        self.assertTrue(u.is_active)
        self.assertEqual(u.role, User.Role.SUPERADMIN)
        self.assertTrue(changes)

    def test_idempotent_second_call_no_changes(self):
        u = User.objects.create_user(
            username="svc2", email="svc2@example.com", password="x"
        )
        apply_superadmin_change(u)
        self.assertEqual(apply_superadmin_change(u), [])
        self.assertEqual(compute_superadmin_changes(u), [])

    def test_demote_clears_flags_but_leaves_role_and_active(self):
        u = User.objects.create_superuser(
            username="svc3", email="svc3@example.com", password="x"
        )
        u.role = User.Role.SUPERADMIN
        u.save(update_fields=["role"])
        changes = apply_superadmin_change(u, demote=True)
        u.refresh_from_db()
        self.assertFalse(u.is_superuser)
        self.assertFalse(u.is_staff)
        self.assertTrue(u.is_active)  # never locks the account
        self.assertEqual(u.role, User.Role.SUPERADMIN)  # role left as-is
        self.assertTrue(changes)

    def test_compute_previews_without_writing(self):
        u = User.objects.create_user(
            username="svc4", email="svc4@example.com", password="x"
        )
        preview = compute_superadmin_changes(u)
        u.refresh_from_db()
        self.assertFalse(u.is_superuser)  # compute did not persist
        self.assertTrue(any("is_superuser" in c for c in preview))
