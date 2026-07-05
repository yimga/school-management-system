"""Wave E — operator-assisted MFA-lockout recovery."""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.management.commands.reset_user_mfa import reset_mfa_for_user
from apps.accounts.models import User


class ResetUserMfaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="locked", password="x", role=User.Role.ADMIN, email="locked@ex.com"
        )

    def _add_devices(self):
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=self.user, name="default", confirmed=True)
        StaticDevice.objects.create(user=self.user, name="backup", confirmed=True)

    def test_reset_removes_devices(self):
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice

        self._add_devices()
        counts = reset_mfa_for_user(self.user)
        self.assertEqual(counts["totp"], 1)
        self.assertEqual(counts["static"], 1)
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())

    def test_reset_is_idempotent(self):
        # No devices -> zero removed, no error.
        self.assertEqual(sum(reset_mfa_for_user(self.user).values()), 0)

    def test_command_runs_with_yes(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        self._add_devices()
        call_command("reset_user_mfa", "locked", "--yes")
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())

    def test_command_resolves_by_email(self):
        self._add_devices()
        call_command("reset_user_mfa", "locked@ex.com", "--yes")
        from django_otp.plugins.otp_totp.models import TOTPDevice

        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())

    def test_command_unknown_user_errors(self):
        with self.assertRaises(CommandError):
            call_command("reset_user_mfa", "nobody@example.com", "--yes")
