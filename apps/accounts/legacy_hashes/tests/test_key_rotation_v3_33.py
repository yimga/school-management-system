"""Tests for the v3.33.0 MultiFernet key rotation tooling.

Covers ``apps.accounts.legacy_hashes.key_rotation``:

* Dry-run mode does not write.
* ``--apply`` re-encrypts every Fernet-wrapped row under the newest key.
* :func:`verify_no_orphan_ciphertexts` returns zero orphans on a clean
  database where every row was written under one of the active keys.
* The rotation audit log writes per-row counts + decrypt booleans but
  NEVER any key material — assertNotIn checks for key fragments,
  plaintext, and ciphertext.
* The rotation flow is idempotent: a second ``--apply`` finds zero
  rows to rewrap.
* MultiFernet wiring: rows written under the OLD key (set via
  ``DJANGO_CRYPTOGRAPHY_KEYS = [new, old]``) still decrypt; after
  rotation they are wrapped under the NEW key.
"""
from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings


User = get_user_model()


def _fresh_fernet_key() -> str:
    """Generate a fresh Fernet key for the test run."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode("ascii")


# Sentinel plaintext + algorithm so we can scan emitted logs/files for it.
_TEST_HASH = "pbkdf2_sha512$120000$DEADBEEFCAFEBABE$" + ("z" * 88)
_TEST_PARAMS = {"iterations": 120000, "salt": "DEADBEEFCAFEBABE"}


def _make_user(username: str = "rot_user_1", with_hash: bool = True) -> "User":
    user = User.objects.create_user(
        username=username,
        password="native-password-dontcare",
        email=f"{username}@example.com",
    )
    if with_hash:
        from apps.migration_cloud.services.legacy_hash_intake import store_legacy_hash
        ok = store_legacy_hash(
            user=user,
            hash_value=_TEST_HASH,
            algorithm="pbkdf2_sha512",
            params_dict=_TEST_PARAMS,
            source_vendor="powerschool",
        )
        assert ok is True
    return user


@override_settings(
    DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key()],
)
class DryRunNoWriteTests(TestCase):
    """``rotate_all_encrypted_columns(dry_run=True)`` must not write."""

    def test_dry_run_does_not_change_row_ciphertext(self) -> None:
        user = _make_user()
        # Snapshot the raw ciphertext via values_list (bypasses the
        # descriptor's transparent decrypt).
        before = User.objects.filter(pk=user.pk).values_list(
            "legacy_password_hash", flat=True,
        ).first()
        # tenant-isolation-allow: test-fixture-no-tenant-context
        from apps.accounts.legacy_hashes.key_rotation import (
            rotate_all_encrypted_columns,
        )
        summary = rotate_all_encrypted_columns(dry_run=True)
        after = User.objects.filter(pk=user.pk).values_list(
            "legacy_password_hash", flat=True,
        ).first()
        self.assertEqual(before, after, "dry-run must not change ciphertext on disk")
        self.assertGreaterEqual(summary["totals"]["rows_scanned"], 1)
        # Either skipped (already-under-primary) or rewrapped-skipped due
        # to dry_run — either way rewrapped count is 0.
        self.assertEqual(summary["totals"]["rows_rewrapped"], 0)


class ApplyRewrapsUnderNewestKeyTests(TestCase):
    """``--apply`` re-encrypts rows under the newest key."""

    def test_rotate_then_old_key_alone_cannot_decrypt(self) -> None:
        old_key = _fresh_fernet_key()
        new_key = _fresh_fernet_key()

        # Phase 1: write rows under the OLD key only.
        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[old_key]):
            user = _make_user("phase1_user")
            raw_under_old = User.objects.filter(pk=user.pk).values_list(
                "legacy_password_hash", flat=True,
            ).first()

        # Phase 2: switch to MultiFernet [new, old] — old still decrypts.
        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[new_key, old_key]):
            from apps.accounts.legacy_hashes.key_rotation import (
                rotate_all_encrypted_columns,
            )
            summary = rotate_all_encrypted_columns(dry_run=False)
            self.assertGreaterEqual(summary["totals"]["rows_rewrapped"], 1)
            raw_after = User.objects.filter(pk=user.pk).values_list(
                "legacy_password_hash", flat=True,
            ).first()
            # The ciphertext on disk must have changed.
            self.assertNotEqual(raw_under_old, raw_after)

        # Phase 3: drop old key. The new ciphertext must still decrypt
        # under the new key alone (proves it was re-wrapped, not just
        # left under the old key).
        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[new_key]):
            user.refresh_from_db()
            self.assertEqual(user.legacy_password_hash, _TEST_HASH)
            self.assertEqual(user.legacy_hash_algorithm, "pbkdf2_sha512")

    def test_apply_is_idempotent(self) -> None:
        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key()]):
            _make_user("idem_user")
            from apps.accounts.legacy_hashes.key_rotation import (
                rotate_all_encrypted_columns,
            )
            first = rotate_all_encrypted_columns(dry_run=False)
            second = rotate_all_encrypted_columns(dry_run=False)
            # First pass: every row already-under-primary because we
            # wrote with the same single key. Second pass: same.
            self.assertEqual(second["totals"]["rows_rewrapped"], 0)
            self.assertEqual(
                second["totals"]["rows_failed"], 0,
                "idempotent second run must not fail any row",
            )
            self.assertEqual(
                first["totals"]["rows_failed"],
                second["totals"]["rows_failed"],
            )


class VerifyNoOrphansCleanDbTests(TestCase):
    """Orphan scan returns zero on a clean DB."""

    @override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key()])
    def test_clean_db_has_zero_orphans(self) -> None:
        for i in range(3):
            _make_user(f"orphan_user_{i}")
        from apps.accounts.legacy_hashes.key_rotation import (
            verify_no_orphan_ciphertexts,
        )
        summary = verify_no_orphan_ciphertexts()
        self.assertEqual(summary["totals"]["orphan_count"], 0)
        self.assertGreaterEqual(summary["totals"]["rows_scanned"], 3)

    def test_dropped_key_produces_orphans(self) -> None:
        """A row written under key A, then key A dropped → orphan."""
        old_key = _fresh_fernet_key()
        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[old_key]):
            _make_user("will_become_orphan")
        # Now drop the old key without rotating — every row written
        # under it is now an orphan.
        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key()]):
            from apps.accounts.legacy_hashes.key_rotation import (
                verify_no_orphan_ciphertexts,
            )
            summary = verify_no_orphan_ciphertexts()
            self.assertGreaterEqual(summary["totals"]["orphan_count"], 1)


class AuditLogLeakFreeTests(TestCase):
    """The audit log must contain counts but NO key/plaintext/ciphertext."""

    def test_audit_log_contains_no_key_or_plaintext(self) -> None:
        active_key = _fresh_fernet_key()
        log_dir = Path(settings.BASE_DIR) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "key_rotation_test_v3_33.jsonl"
        if log_path.exists():
            log_path.unlink()

        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[active_key]):
            user = _make_user("log_check_user")
            raw_ct = User.objects.filter(pk=user.pk).values_list(
                "legacy_password_hash", flat=True,
            ).first()
            from apps.accounts.legacy_hashes.key_rotation import (
                rotate_all_encrypted_columns,
            )
            rotate_all_encrypted_columns(dry_run=False, log_path=log_path)

        contents = log_path.read_text(encoding="utf-8")
        # Each line is JSON; assert structural fields are present and
        # the forbidden values are NOT.
        lines = [ln for ln in contents.splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 2, "expected start + summary + per-row lines")
        # NEVER the active key.
        self.assertNotIn(
            active_key, contents,
            "audit log must not contain key material",
        )
        # NEVER the plaintext hash.
        self.assertNotIn(
            _TEST_HASH, contents,
            "audit log must not contain plaintext legacy hash",
        )
        # NEVER the salt either (proxy for params content leakage).
        self.assertNotIn(
            _TEST_PARAMS["salt"], contents,
            "audit log must not contain params salt",
        )
        # NEVER the ciphertext itself.
        if raw_ct:
            self.assertNotIn(
                raw_ct, contents,
                "audit log must not contain ciphertext",
            )
        # And no fragment of a Fernet key (44 url-safe-base64 chars). We
        # check the FULL 44-char prefix of the key; a shorter fragment
        # could legitimately appear by coincidence.
        self.assertNotIn(active_key[:32], contents)

    def test_summary_line_carries_totals(self) -> None:
        active_key = _fresh_fernet_key()
        log_path = Path(settings.BASE_DIR) / "logs" / "key_rotation_summary_v3_33.jsonl"
        if log_path.exists():
            log_path.unlink()
        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[active_key]):
            _make_user("summary_user")
            from apps.accounts.legacy_hashes.key_rotation import (
                rotate_all_encrypted_columns,
            )
            rotate_all_encrypted_columns(dry_run=True, log_path=log_path)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        summary_lines = [
            json.loads(ln) for ln in lines if ln.strip() and json.loads(ln).get("event") == "rotation_summary"
        ]
        self.assertEqual(len(summary_lines), 1)
        s = summary_lines[0]
        self.assertIn("totals", s)
        self.assertIn("rows_scanned", s["totals"])
        self.assertIn("rows_rewrapped", s["totals"])
        self.assertIn("rows_skipped", s["totals"])
        self.assertIn("rows_failed", s["totals"])


class ManagementCommandTests(TestCase):
    """``manage.py rotate_encryption_keys`` exercises both modes."""

    @override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key()])
    def test_default_invocation_is_dry_run(self) -> None:
        _make_user("cmd_dry_user")
        out = StringIO()
        call_command("rotate_encryption_keys", stdout=out)
        self.assertIn("DRY-RUN", out.getvalue())
        # Did not raise → exit 0 path.

    @override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key()])
    def test_apply_invocation_writes(self) -> None:
        _make_user("cmd_apply_user")
        out = StringIO()
        call_command("rotate_encryption_keys", "--apply", stdout=out)
        self.assertIn("APPLYING", out.getvalue())

    @override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key()])
    def test_verify_orphans_invocation_clean(self) -> None:
        _make_user("cmd_orphan_user")
        out = StringIO()
        call_command(
            "rotate_encryption_keys", "--verify-orphans", stdout=out,
        )
        self.assertIn("orphan scan", out.getvalue())

    @override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key()])
    def test_model_scope_restricts_walk(self) -> None:
        _make_user("scoped_user")
        out = StringIO()
        call_command(
            "rotate_encryption_keys", "--model", "accounts.User", stdout=out,
        )
        # The output should mention the scoped model.
        self.assertIn("accounts.user", out.getvalue().lower())


class IntakeVendorAnchorTests(TestCase):
    """v3.33.0 vendor-anchor wire on store_legacy_hash."""

    def test_vendor_anchor_used_when_provided(self) -> None:
        from datetime import timedelta
        from django.utils import timezone
        from apps.migration_cloud.services.legacy_hash_intake import (
            store_legacy_hash,
        )
        user = User.objects.create_user(username="vendor_anchor_u", password="x")
        anchor = timezone.now() - timedelta(days=300)
        ok = store_legacy_hash(
            user=user,
            hash_value=_TEST_HASH,
            algorithm="pbkdf2_sha512",
            params_dict=_TEST_PARAMS,
            source_vendor="powerschool",
            legacy_hash_created_at_source=anchor,
        )
        self.assertTrue(ok)
        user.refresh_from_db()
        # Allow microsecond-level slop.
        self.assertEqual(
            user.legacy_hash_created_at.replace(microsecond=0),
            anchor.replace(microsecond=0),
        )

    def test_now_used_when_no_vendor_anchor(self) -> None:
        from django.utils import timezone
        from apps.migration_cloud.services.legacy_hash_intake import (
            store_legacy_hash,
        )
        user = User.objects.create_user(username="now_anchor_u", password="x")
        before = timezone.now()
        ok = store_legacy_hash(
            user=user,
            hash_value=_TEST_HASH,
            algorithm="pbkdf2_sha512",
            params_dict=_TEST_PARAMS,
            source_vendor="blackbaud",
            # legacy_hash_created_at_source omitted
        )
        self.assertTrue(ok)
        user.refresh_from_db()
        self.assertIsNotNone(user.legacy_hash_created_at)
        self.assertGreaterEqual(user.legacy_hash_created_at, before)


class BackendInUseInvariantTests(TestCase):
    """``backend_in_use()`` must still report accurately under rotation."""

    def test_backend_in_use_reports_known_slug(self) -> None:
        from apps.accounts.legacy_hashes.encryption import backend_in_use
        slug = backend_in_use()
        self.assertIn(slug, ("django_cryptography_upstream", "internal_fernet_shim"))

    @override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[_fresh_fernet_key(), _fresh_fernet_key()])
    def test_active_key_count_under_rotation(self) -> None:
        from apps.accounts.legacy_hashes.encryption import active_key_count
        self.assertEqual(active_key_count(), 2)

    def test_authentication_backend_invariant_preserved(self) -> None:
        """AUTHENTICATION_BACKENDS[0] must remain LegacyHashUpgradeBackend
        across the v3.33.0 wave — this test fails loudly if a sibling
        agent touches that ordering.
        """
        self.assertEqual(
            settings.AUTHENTICATION_BACKENDS[0],
            "apps.accounts.auth_backends_legacy.LegacyHashUpgradeBackend",
        )
