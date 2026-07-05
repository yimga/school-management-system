"""Operator recovery: reset (remove) a user's MFA devices so they can re-enroll.

For MFA lockout — an owner/admin who lost their authenticator AND has exhausted or
never saved their one-time backup codes. Removing their MFA devices forces a fresh
enrollment on next login. Requires shell/deploy access (a platform operator), which
is the right blast-radius gate for a recovery primitive. Audited to the security log.

    python manage.py reset_user_mfa <username-or-email> [--yes]
"""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

logger = logging.getLogger("security.account_recovery")


def reset_mfa_for_user(user) -> dict:
    """Remove all MFA devices for ``user``; returns per-type removal counts.

    Idempotent and defensive: a missing plugin or DB error for one device type is
    swallowed so the others still clear. On next login the user has no confirmed
    device and is routed back through MFA enrollment.
    """
    counts = {"totp": 0, "static": 0, "passkey": 0}
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice

        counts["totp"] = TOTPDevice.objects.filter(user=user).delete()[0]
    except (ImportError, DatabaseError, AttributeError):
        pass
    try:
        from django_otp.plugins.otp_static.models import StaticDevice

        counts["static"] = StaticDevice.objects.filter(user=user).delete()[0]
    except (ImportError, DatabaseError, AttributeError):
        pass
    try:
        from apps.accounts.models import UserPasskey

        counts["passkey"] = UserPasskey.objects.filter(user=user).delete()[0]
    except (ImportError, DatabaseError, AttributeError):
        pass
    return counts


class Command(BaseCommand):
    help = (
        "Reset a user's MFA (remove TOTP/backup/passkey devices) so they re-enroll on "
        "next login. Operator recovery for an MFA-locked-out owner/admin."
    )

    def add_arguments(self, parser):
        parser.add_argument("identifier", help="username or email of the locked-out user")
        parser.add_argument(
            "--yes", action="store_true", help="skip the interactive confirmation prompt"
        )

    def handle(self, *args, **options):
        User = get_user_model()
        ident = (options["identifier"] or "").strip()
        user = (
            User.objects.filter(username=ident).first()
            or User.objects.filter(email__iexact=ident).first()
        )
        if not user:
            raise CommandError(f"No user matching {ident!r}.")

        if not options["yes"]:
            self.stdout.write(
                f"About to remove ALL MFA devices for {user.username} (id={user.pk}). "
                "They will re-enroll on next login."
            )
            if input("Type 'yes' to proceed: ").strip().lower() != "yes":
                raise CommandError("Aborted.")

        counts = reset_mfa_for_user(user)
        total = sum(counts.values())
        logger.warning(
            "account_recovery.mfa_reset user_id=%s username=%s removed=%s",
            user.pk,
            user.username,
            counts,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {total} MFA device(s) for {user.username} "
                f"(totp={counts['totp']}, backup={counts['static']}, passkey={counts['passkey']}). "
                "They will set up MFA again on next sign-in."
            )
        )
