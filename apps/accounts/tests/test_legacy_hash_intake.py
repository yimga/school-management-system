"""Tests for the v3.32.0 canonical legacy-hash intake helper.

Covers ``apps.migration_cloud.services.legacy_hash_intake``:

  * ``store_legacy_hash`` writes all four legacy fields (including
    ``legacy_hash_created_at``).
  * Logger never sees the hash, the salt, or the password — extension
    of v3.28/v3.29's ``NoSecretsLoggedTests`` pattern.
  * Unknown algorithm rejected with ``ValueError`` at intake (not
    silently stored to fail at first login).
  * Re-storing on the same user overwrites cleanly + bumps the anchor.
  * Tenant isolation: only the target user's row is touched.
  * The v3.29 sunset task still finds the right cohort after intake
    (regression — proves the wire didn't break the FSM).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.legacy_hashes import sunset_task
from apps.migration_cloud.services.legacy_hash_intake import (
    INTAKE_FIELDS,
    store_legacy_hash,
)


User = get_user_model()


# A plausible PowerSchool-style PBKDF2-SHA512 hash for round-tripping
# through the helper — we never verify it, the helper only writes it.
_FAKE_PS_HASH = "pbkdf2_sha512$120000$" + "a" * 16 + "$" + "b" * 88
_FAKE_PS_PARAMS = {"iterations": 120000, "salt": "a" * 16}
# Sentinel value the NoSecretsLogged test will scan for — must never
# appear in any logger record after we hand it to store_legacy_hash.
_SECRET_MARKER = "PLEASE-NEVER-LOG-THIS-DEADBEEF-LEGACY-HASH"


class LegacyHashIntakeBasicTests(TestCase):
    """Happy-path + field-coverage assertions."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="ps_user_1",
            password="dontcare-native-password",
            email="ps_user_1@example.com",
        )

    def test_store_sets_all_four_fields(self) -> None:
        before = timezone.now()
        ok = store_legacy_hash(
            self.user,
            _FAKE_PS_HASH,
            "pbkdf2_sha512",
            _FAKE_PS_PARAMS,
            source_vendor="powerschool",
        )
        self.assertTrue(ok)
        self.user.refresh_from_db()
        self.assertEqual(self.user.legacy_password_hash, _FAKE_PS_HASH)
        self.assertEqual(self.user.legacy_hash_algorithm, "pbkdf2_sha512")
        self.assertEqual(self.user.legacy_hash_params, _FAKE_PS_PARAMS)
        # Anchor stamped within the test window.
        self.assertIsNotNone(self.user.legacy_hash_created_at)
        self.assertGreaterEqual(self.user.legacy_hash_created_at, before)

    def test_intake_fields_constant_matches_save_call(self) -> None:
        # Module-constant contract — if a future edit drops one of the
        # four fields, this test makes the regression obvious.
        self.assertIn("legacy_password_hash", INTAKE_FIELDS)
        self.assertIn("legacy_hash_algorithm", INTAKE_FIELDS)
        self.assertIn("legacy_hash_params", INTAKE_FIELDS)
        self.assertIn("legacy_hash_created_at", INTAKE_FIELDS)


class LegacyHashIntakeValidationTests(TestCase):
    """Invalid inputs raise ``ValueError`` before any DB write."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="val_user_1",
            password="dontcare",
        )

    def test_unknown_algorithm_rejected(self) -> None:
        with self.assertRaises(ValueError):
            store_legacy_hash(
                self.user, "abc", "not_a_real_algorithm_slug", {},
            )
        self.user.refresh_from_db()
        self.assertEqual(self.user.legacy_password_hash, "")

    def test_empty_hash_rejected(self) -> None:
        with self.assertRaises(ValueError):
            store_legacy_hash(self.user, "", "pbkdf2_sha512", {})

    def test_non_user_rejected(self) -> None:
        with self.assertRaises(ValueError):
            store_legacy_hash(
                {"pk": 1}, "abc", "pbkdf2_sha512", {},
            )


class LegacyHashIntakeNoSecretsLoggedTests(TestCase):
    """Logger must NEVER see the hash, salt, or any secret bytes."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="nolog_user",
            password="dontcare",
        )

    def test_logger_never_records_secret_or_salt(self) -> None:
        salt_marker = "PLEASE-NEVER-LOG-THIS-SALT-CAFEBABE"
        with self.assertLogs(
            "apps.migration_cloud.services.legacy_hash_intake",
            level="INFO",
        ) as cm:
            store_legacy_hash(
                self.user,
                _SECRET_MARKER,
                "pbkdf2_sha512",
                {"iterations": 120000, "salt": salt_marker},
                source_vendor="powerschool",
            )
        blob = "\n".join(cm.output)
        self.assertNotIn(_SECRET_MARKER, blob)
        self.assertNotIn(salt_marker, blob)
        # But the algorithm name + vendor slug SHOULD be present —
        # those are operator-visible metadata, not secrets.
        self.assertIn("pbkdf2_sha512", blob)
        self.assertIn("powerschool", blob)


class LegacyHashIntakeOverwriteTests(TestCase):
    """Re-storing overwrites cleanly + bumps the anchor."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="overwrite_user", password="dontcare",
        )

    def test_second_store_replaces_first(self) -> None:
        ok = store_legacy_hash(
            self.user, _FAKE_PS_HASH, "pbkdf2_sha512", _FAKE_PS_PARAMS,
        )
        self.assertTrue(ok)
        self.user.refresh_from_db()
        first_anchor = self.user.legacy_hash_created_at

        # A short pause is not needed — timezone.now() advances per
        # microsecond. But the anchor should be >= the first.
        ok2 = store_legacy_hash(
            self.user,
            "different-hash-value",
            "bcrypt",
            {"cost": 12},
            source_vendor="blackbaud",
        )
        self.assertTrue(ok2)
        self.user.refresh_from_db()
        self.assertEqual(self.user.legacy_password_hash, "different-hash-value")
        self.assertEqual(self.user.legacy_hash_algorithm, "bcrypt")
        self.assertEqual(self.user.legacy_hash_params, {"cost": 12})
        self.assertGreaterEqual(
            self.user.legacy_hash_created_at, first_anchor,
        )


class LegacyHashIntakeIsolationTests(TestCase):
    """Storing for user A must not touch user B's row."""

    def setUp(self) -> None:
        self.alice = User.objects.create_user(
            username="alice_isolation", password="dontcare",
        )
        self.bob = User.objects.create_user(
            username="bob_isolation", password="dontcare",
        )

    def test_only_target_user_row_updated(self) -> None:
        store_legacy_hash(
            self.alice, _FAKE_PS_HASH, "pbkdf2_sha512", _FAKE_PS_PARAMS,
        )
        self.alice.refresh_from_db()
        self.bob.refresh_from_db()
        self.assertNotEqual(self.alice.legacy_password_hash, "")
        self.assertEqual(self.bob.legacy_password_hash, "")
        self.assertIsNone(self.bob.legacy_hash_created_at)


class LegacyHashIntakeSunsetRegressionTests(TestCase):
    """The v3.29 sunset job still finds the right cohort after intake."""

    def test_freshly_intaken_user_is_not_email_eligible(self) -> None:
        # A user we just stored a hash for has legacy_hash_created_at
        # = now() — they are NOT 12 months old yet, so the sunset job
        # should report 0 eligible.
        user = User.objects.create_user(
            username="freshly_intaken", password="dontcare",
            email="fresh@example.com",
        )
        store_legacy_hash(
            user, _FAKE_PS_HASH, "pbkdf2_sha512", _FAKE_PS_PARAMS,
            source_vendor="powerschool",
        )
        result = sunset_task.sunset_stale_legacy_hashes(dry_run=True)
        self.assertEqual(result["eligible"], 0)

    def test_old_intaken_user_is_email_eligible(self) -> None:
        # Backdate legacy_hash_created_at by 13 months → eligible.
        user = User.objects.create_user(
            username="old_intaken", password="dontcare",
            email="old@example.com",
        )
        store_legacy_hash(
            user, _FAKE_PS_HASH, "pbkdf2_sha512", _FAKE_PS_PARAMS,
            source_vendor="powerschool",
        )
        user.legacy_hash_created_at = timezone.now() - timedelta(days=400)
        user.save(update_fields=["legacy_hash_created_at"])
        result = sunset_task.sunset_stale_legacy_hashes(dry_run=True)
        self.assertGreaterEqual(result["eligible"], 1)
