"""Tests for the operator-only platform-superadmin console.

Verifies the surface is control-plane-gated and that minting god-mode is
superuser-only (only a superuser can make a superuser).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class OperatorSuperadminConsoleTests(TestCase):
    def setUp(self):
        self.url = reverse("super:superadmin_console")

    def test_regular_user_denied(self):
        u = User.objects.create_user(
            username="reg", email="reg@example.com", password="x"
        )
        self.client.force_login(u)
        resp = self.client.get(self.url)
        self.assertNotEqual(resp.status_code, 200)

    def test_superuser_can_view_and_promote(self):
        admin = User.objects.create_superuser(
            username="root", email="root@example.com", password="x"
        )
        target = User.objects.create_user(
            username="t1", email="t1@example.com", password="x"
        )
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.post(self.url, {"action": "promote", "user_id": target.pk})
        target.refresh_from_db()
        self.assertTrue(target.is_superuser)
        self.assertTrue(target.is_staff)

    def test_superuser_can_demote(self):
        admin = User.objects.create_superuser(
            username="root2", email="root2@example.com", password="x"
        )
        target = User.objects.create_superuser(
            username="t2", email="t2@example.com", password="x"
        )
        self.client.force_login(admin)
        self.client.post(self.url, {"action": "demote", "user_id": target.pk})
        target.refresh_from_db()
        self.assertFalse(target.is_superuser)

    def test_control_plane_non_superuser_cannot_mint(self):
        # role=SUPERADMIN + no SchoolMembership -> control-plane access (can VIEW),
        # but the mint action requires the actor to already be is_superuser.
        operator = User.objects.create_user(
            username="op", email="op@example.com", password="x",
            role=User.Role.SUPERADMIN,
        )
        target = User.objects.create_user(
            username="t3", email="t3@example.com", password="x"
        )
        self.client.force_login(operator)
        # SUPERADMIN is an MFA-required operator role, so this user (unlike the
        # role-less superusers in the sibling tests) hits the operator MFA gate.
        # Enroll + verify so the control-plane GET renders (200); the POST mint
        # gate below (403, actor is not is_superuser) is what this test guards.
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=operator, name="op-totp", confirmed=True)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        resp = self.client.post(
            self.url, {"action": "promote", "user_id": target.pk}
        )
        self.assertEqual(resp.status_code, 403)
        target.refresh_from_db()
        self.assertFalse(target.is_superuser)
