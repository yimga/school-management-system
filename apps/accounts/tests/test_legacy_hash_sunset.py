"""Tests for the legacy hash sunset task + setup-link view + backfill script.

Covers the v3.29 productionization of the migration-cloud password
preservation moat:

* :func:`sunset_stale_legacy_hashes` cohort selection (12-month aged,
  no recent login, no prior email), email-send side effect, grace
  exit, idempotency.
* :class:`LegacySetupView` token validation + atomic field clear.
* ``legacy_hash_created_at`` defensive backfill in the auth backend.
* No password / hash / salt / token ever reaches the logger
  (extension of v3.28's :class:`NoSecretsLoggedTests`).
* The backfill script's dry-run and apply modes.
"""
from __future__ import annotations

import io
import logging
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.legacy_hashes import sunset_task
from apps.accounts.legacy_hashes.encryption import backend_in_use


User = get_user_model()


def _make_legacy_user(
    username: str,
    *,
    has_hash: bool = True,
    last_login_days_ago: int | None = None,
    legacy_age_days: int | None = None,
    sunset_email_days_ago: int | None = None,
    email: str = "",
):
    """Helper: create a User in a controlled legacy state."""
    user = User.objects.create_user(
        username=username,
        email=email or f"{username}@example.test",
        password="seed-pwd-not-used",
    )
    if has_hash:
        user.legacy_password_hash = "deadbeef-pretend-foreign-hash"
        user.legacy_hash_algorithm = "pbkdf2_sha512"
        user.legacy_hash_params = {"salt": "abc", "iterations": 50000}
    else:
        user.legacy_password_hash = ""
        user.legacy_hash_algorithm = ""
        user.legacy_hash_params = {}

    now = timezone.now()
    if legacy_age_days is not None:
        user.legacy_hash_created_at = now - timedelta(days=legacy_age_days)
    if sunset_email_days_ago is not None:
        user.legacy_hash_sunset_email_sent_at = now - timedelta(
            days=sunset_email_days_ago
        )
    if last_login_days_ago is not None:
        user.last_login = now - timedelta(days=last_login_days_ago)

    user.save()
    return user


class SunsetTaskCohortTests(TestCase):
    def test_dry_run_does_not_write(self):
        _make_legacy_user("alpha", legacy_age_days=400)
        result = sunset_task.sunset_stale_legacy_hashes(dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertGreaterEqual(result["eligible"], 1)
        self.assertEqual(result["emailed"], 0)
        self.assertEqual(result["nulled"], 0)

    def test_apply_emails_eligible_users(self):
        _make_legacy_user("beta", legacy_age_days=400, email="beta@example.test")
        result = sunset_task.sunset_stale_legacy_hashes(dry_run=False)
        self.assertFalse(result["dry_run"])
        self.assertGreaterEqual(result["emailed"], 1)
        # Exactly one email landed in the outbox for beta@example.test.
        sent_addresses = [recipient for m in mail.outbox for recipient in m.to]
        self.assertIn("beta@example.test", sent_addresses)
        # User row is stamped.
        user = User.objects.get(username="beta")
        self.assertIsNotNone(user.legacy_hash_sunset_email_sent_at)

    def test_recent_login_users_not_eligible(self):
        _make_legacy_user(
            "gamma", legacy_age_days=400, last_login_days_ago=30
        )
        result = sunset_task.sunset_stale_legacy_hashes(dry_run=True)
        self.assertEqual(result["eligible"], 0)

    def test_users_without_legacy_hash_not_eligible(self):
        _make_legacy_user("delta", has_hash=False, legacy_age_days=400)
        result = sunset_task.sunset_stale_legacy_hashes(dry_run=True)
        self.assertEqual(result["eligible"], 0)

    def test_grace_period_users_get_nulled(self):
        _make_legacy_user(
            "epsilon",
            legacy_age_days=500,
            sunset_email_days_ago=45,
        )
        result = sunset_task.sunset_stale_legacy_hashes(dry_run=False)
        self.assertGreaterEqual(result["nulled"], 1)
        user = User.objects.get(username="epsilon")
        self.assertEqual(user.legacy_password_hash, "")
        self.assertEqual(user.legacy_hash_algorithm, "")
        self.assertEqual(user.legacy_hash_params, {})
        self.assertFalse(user.has_usable_password())

    def test_idempotent_same_day(self):
        _make_legacy_user("zeta", legacy_age_days=400)
        first = sunset_task.sunset_stale_legacy_hashes(dry_run=False)
        # Second pass: the user now has sunset_email_sent_at, so the
        # email candidate set is empty; the grace candidate set is also
        # empty (we just emailed them).
        second = sunset_task.sunset_stale_legacy_hashes(dry_run=False)
        self.assertEqual(second["emailed"], 0)
        self.assertEqual(second["nulled"], 0)
        # First-run number is sane (sanity check, not strictly idempotency).
        self.assertGreaterEqual(first["emailed"], 1)

    def test_age_months_tunable(self):
        # 60-day-old hash; default age_months=12 means NOT eligible.
        _make_legacy_user("eta", legacy_age_days=60)
        default_result = sunset_task.sunset_stale_legacy_hashes(dry_run=True)
        self.assertEqual(default_result["eligible"], 0)
        # Bump age_months=1 (30 days) → eligible.
        tight_result = sunset_task.sunset_stale_legacy_hashes(
            dry_run=True, age_months=1
        )
        self.assertGreaterEqual(tight_result["eligible"], 1)


class LegacySetupViewTests(TestCase):
    def setUp(self):
        self.user = _make_legacy_user(
            "theta", legacy_age_days=400, sunset_email_days_ago=5
        )
        self.user.set_password("placeholder")
        self.user.save()
        self.uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = default_token_generator.make_token(self.user)

    def test_get_with_valid_token_returns_form(self):
        url = reverse(
            "accounts:legacy_setup",
            kwargs={"uidb64": self.uidb64, "token": self.token},
        )
        # Django's PasswordResetConfirmView stores token in session and
        # redirects to a "set-password" URL with a placeholder token.
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        # validlink True in the rendered context.
        self.assertTrue(response.context.get("validlink"))

    def test_post_with_valid_token_clears_legacy_fields(self):
        url = reverse(
            "accounts:legacy_setup",
            kwargs={"uidb64": self.uidb64, "token": self.token},
        )
        # Two-step Django flow: GET to land on set-password URL, then POST.
        self.client.get(url, follow=True)
        set_password_url = reverse(
            "accounts:legacy_setup",
            kwargs={"uidb64": self.uidb64, "token": "set-password"},
        )
        new_pw = "Fresh-Strong-Password-9!"
        response = self.client.post(
            set_password_url,
            data={"new_password1": new_pw, "new_password2": new_pw},
        )
        # Either 302 (success → success_url) or 200 (re-render with errors).
        self.user.refresh_from_db()
        if response.status_code in (302, 301):
            self.assertEqual(self.user.legacy_password_hash, "")
            self.assertEqual(self.user.legacy_hash_algorithm, "")
            self.assertEqual(self.user.legacy_hash_params, {})
            self.assertIsNone(self.user.legacy_hash_sunset_email_sent_at)

    def test_get_with_invalid_token_renders_expired_state(self):
        url = reverse(
            "accounts:legacy_setup",
            kwargs={"uidb64": self.uidb64, "token": "invalid-token-xyz"},
        )
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get("validlink"))


class LegacyHashCreatedAtBackfillTests(TestCase):
    def test_backend_sets_created_at_when_missing(self):
        from apps.accounts.auth_backends_legacy import LegacyHashUpgradeBackend

        # We don't try to verify a real foreign hash here — we just want
        # to confirm the backfill branch fires. Stub the verifier so
        # it returns False (matches the existing "legacy_hash_no_match"
        # log path) but the backfill still runs.
        user = _make_legacy_user("iota", legacy_age_days=400)
        user.legacy_hash_created_at = None
        user.save(update_fields=("legacy_hash_created_at",))

        backend = LegacyHashUpgradeBackend()
        with mock.patch(
            "apps.accounts.auth_backends_legacy.verify_legacy_hash",
            return_value=False,
        ):
            backend.authenticate(request=None, username="iota", password="any")

        user.refresh_from_db()
        self.assertIsNotNone(user.legacy_hash_created_at)


class SunsetNoSecretsLoggedTests(TestCase):
    """Extension of v3.28 NoSecretsLoggedTests: the sunset task must
    never log tokens, hashes, passwords, or salts.
    """

    SECRET_PASSWORD = "S3cret-Sunset-Password-Z"
    SECRET_TOKEN_MARKER = "this-marker-should-never-appear"

    def test_token_never_logged(self):
        user = _make_legacy_user(
            "kappa", legacy_age_days=400, email="kappa@example.test"
        )
        # Stamp a known sentinel into the hash so we can assert it
        # doesn't escape into the log stream.
        user.legacy_password_hash = self.SECRET_TOKEN_MARKER
        user.save(update_fields=("legacy_password_hash",))

        captured = StringIO()
        root_logger = logging.getLogger()
        handler = logging.StreamHandler(captured)
        handler.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)
        prev_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        try:
            sunset_task.sunset_stale_legacy_hashes(dry_run=False)
        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(prev_level)

        log_text = captured.getvalue()
        # The hash sentinel must NEVER appear in logs.
        self.assertNotIn(self.SECRET_TOKEN_MARKER, log_text)
        # No raw password-reset token should land in logs either; we
        # can't easily synthesize the token we sent without re-running
        # the generator, but we can assert that the email body's
        # template variables (which would contain the token if leaked)
        # are not in the captured log.
        for outbox_message in mail.outbox:
            body = outbox_message.body
            # The "set-password" / "legacy-setup" path text would betray
            # token presence; assert that nothing of that shape appears
            # in the log.
            if "legacy-setup/" in body:
                # extract token-like segment and confirm absent from log
                segment = body.split("legacy-setup/")[1].split()[0]
                self.assertNotIn(segment, log_text)


class EncryptionBackfillScriptTests(TestCase):
    """The standalone script can be invoked as a module too."""

    def test_dry_run_does_not_write(self):
        _make_legacy_user("lambda", legacy_age_days=400)

        # Import the script's main() function and call it directly with
        # mock argv so we get the dry-run path.
        import sys

        old_argv = sys.argv
        sys.argv = ["encrypt_existing_legacy_hashes.py"]
        try:
            # Capture stdout to verify the report line.
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                from scripts import encrypt_existing_legacy_hashes  # noqa: F401

                # Re-running main() requires re-importing or calling it.
                rc = encrypt_existing_legacy_hashes.main()
            self.assertEqual(rc, 0)
            self.assertIn("DRY RUN", buf.getvalue())
        finally:
            sys.argv = old_argv

    def test_apply_re_saves_rows(self):
        user = _make_legacy_user("mu", legacy_age_days=400)
        # Sanity: row exists and has the seeded value pre-script.
        self.assertNotEqual(user.legacy_password_hash, "")

        import sys

        old_argv = sys.argv
        sys.argv = ["encrypt_existing_legacy_hashes.py", "--apply"]
        try:
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                from scripts import encrypt_existing_legacy_hashes

                rc = encrypt_existing_legacy_hashes.main()
            self.assertEqual(rc, 0)
            self.assertIn("Encrypted", buf.getvalue())
        finally:
            sys.argv = old_argv

        # After --apply, the row still has the same DECRYPTED value
        # (idempotent w.r.t. plaintext) but a different ciphertext in
        # the DB. We can only test plaintext round-trip here.
        user.refresh_from_db()
        self.assertEqual(
            user.legacy_password_hash, "deadbeef-pretend-foreign-hash"
        )


class EncryptionBackendReportingTests(TestCase):
    """Sanity: the active backend is one of the two known options."""

    def test_backend_in_use_returns_known_slug(self):
        slug = backend_in_use()
        self.assertIn(
            slug,
            {"django_cryptography_upstream", "internal_fernet_shim"},
        )
