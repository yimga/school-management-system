"""Tests for the v3.34.0 per-vendor `legacy_hash_created_at` extension.

Covers the extended defensive coercion in
``apps.migration_cloud.services.legacy_hash_intake.store_legacy_hash``:

* Per-vendor `legacy_hash_created_at_source` round-trips into
  `User.legacy_hash_created_at` for Blackbaud / Veracross / Alma
  (datetime input + ISO-8601 string input both supported).
* Missing source falls back to `timezone.now()` (within 1 second of
  test execution).
* Malformed source string ("not-a-date") falls back gracefully
  without raising.
* Future-dated source is clamped to `now()` with a structured
  warning (defensive — clock-skew protection).
* NoSecretsLoggedTests via `assertLogs`: never log hash, salt, or
  password during intake (extension of the v3.32.0 pattern).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as _stdlib_tz

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud.services.legacy_hash_intake import store_legacy_hash


User = get_user_model()


# Sentinel hash + algorithm that match a registered verifier slug
# (`bcrypt` is the common BB / Veracross / Alma verifier; `pbkdf2_sha512`
# for the PowerSchool comparison path). NEVER logged.
_FAKE_BCRYPT_HASH = "$2b$12$" + ("a" * 53)
_FAKE_BCRYPT_PARAMS = {"cost": 12}
_FAKE_PS_HASH = "pbkdf2_sha512$120000$" + ("a" * 16) + "$" + ("b" * 88)
_FAKE_PS_PARAMS = {"iterations": 120000, "salt": "a" * 16}

# Hard sentinels for the "never log a secret" assertion.
_HASH_SENTINEL = "NEVER-LOG-THIS-HASH-MARKER-V3-34-DEADBEEF"
_SALT_SENTINEL = "NEVER-LOG-THIS-SALT-MARKER-V3-34-CAFEBABE"


class LegacyHashIntakePerVendorRoundtripTests(TestCase):
    """Datetime + ISO-8601 string anchors round-trip per vendor."""

    def _make_user(self, suffix: str):
        return User.objects.create_user(
            username=f"per_vendor_{suffix}",
            password="dontcare-native",
            email=f"per_vendor_{suffix}@example.com",
        )

    def test_blackbaud_datetime_anchor_roundtrips(self) -> None:
        user = self._make_user("bb_dt")
        # Six months ago — a typical "user-modified-time" approximation.
        anchor = timezone.now() - timedelta(days=180)
        ok = store_legacy_hash(
            user,
            _FAKE_BCRYPT_HASH,
            "bcrypt",
            _FAKE_BCRYPT_PARAMS,
            source_vendor="blackbaud",
            legacy_hash_created_at_source=anchor,
        )
        self.assertTrue(ok)
        user.refresh_from_db()
        # Stored value should equal the input (within a few ms — the
        # helper does not round-trip through any lossy serialization).
        delta = abs(
            (user.legacy_hash_created_at - anchor).total_seconds()
        )
        self.assertLess(delta, 1.0)

    def test_veracross_iso8601_string_anchor_roundtrips(self) -> None:
        user = self._make_user("vc_iso")
        anchor_dt = timezone.now() - timedelta(days=90)
        # Veracross custom report exports timestamps as ISO-8601 strings.
        anchor_iso = anchor_dt.isoformat()
        ok = store_legacy_hash(
            user,
            _FAKE_BCRYPT_HASH,
            "veracross_bcrypt",
            _FAKE_BCRYPT_PARAMS,
            source_vendor="veracross",
            legacy_hash_created_at_source=anchor_iso,
        )
        self.assertTrue(ok)
        user.refresh_from_db()
        self.assertIsNotNone(user.legacy_hash_created_at)
        delta = abs(
            (user.legacy_hash_created_at - anchor_dt).total_seconds()
        )
        self.assertLess(delta, 1.0)

    def test_alma_iso8601_z_suffix_anchor_roundtrips(self) -> None:
        user = self._make_user("alma_z")
        # Alma GraphQL emits timestamps with trailing "Z" for UTC.
        anchor_dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=_stdlib_tz.utc)
        anchor_iso_z = "2025-06-15T12:00:00Z"
        ok = store_legacy_hash(
            user,
            _FAKE_BCRYPT_HASH,
            "alma_bcrypt",
            _FAKE_BCRYPT_PARAMS,
            source_vendor="alma",
            legacy_hash_created_at_source=anchor_iso_z,
        )
        self.assertTrue(ok)
        user.refresh_from_db()
        delta = abs(
            (user.legacy_hash_created_at - anchor_dt).total_seconds()
        )
        self.assertLess(delta, 1.0)


class LegacyHashIntakeFallbackTests(TestCase):
    """Missing / malformed / future-dated sources fall back gracefully."""

    def _make_user(self, suffix: str):
        return User.objects.create_user(
            username=f"fallback_{suffix}",
            password="dontcare-native",
            email=f"fallback_{suffix}@example.com",
        )

    def test_missing_source_falls_back_to_now(self) -> None:
        user = self._make_user("missing")
        before = timezone.now()
        ok = store_legacy_hash(
            user,
            _FAKE_BCRYPT_HASH,
            "bcrypt",
            _FAKE_BCRYPT_PARAMS,
            source_vendor="blackbaud",
            # legacy_hash_created_at_source omitted on purpose
        )
        after = timezone.now()
        self.assertTrue(ok)
        user.refresh_from_db()
        # Anchor should be within the test window — defensive 1s
        # tolerance on each side to absorb scheduler jitter.
        self.assertGreaterEqual(
            user.legacy_hash_created_at,
            before - timedelta(seconds=1),
        )
        self.assertLessEqual(
            user.legacy_hash_created_at,
            after + timedelta(seconds=1),
        )

    def test_malformed_string_source_falls_back_without_raising(self) -> None:
        user = self._make_user("malformed")
        before = timezone.now()
        # Pass clearly-bad string; helper should NOT raise.
        ok = store_legacy_hash(
            user,
            _FAKE_BCRYPT_HASH,
            "bcrypt",
            _FAKE_BCRYPT_PARAMS,
            source_vendor="veracross",
            legacy_hash_created_at_source="not-a-date-at-all",
        )
        self.assertTrue(ok)
        user.refresh_from_db()
        # Fell back to now() — within the test window.
        self.assertGreaterEqual(
            user.legacy_hash_created_at,
            before - timedelta(seconds=1),
        )

    def test_future_dated_source_clamped_to_now_with_warning(self) -> None:
        user = self._make_user("future")
        # 10 minutes in the future — well past the 60-second tolerance.
        future_anchor = timezone.now() + timedelta(minutes=10)
        before = timezone.now()
        with self.assertLogs(
            "apps.migration_cloud.services.legacy_hash_intake",
            level="WARNING",
        ) as cm:
            ok = store_legacy_hash(
                user,
                _FAKE_BCRYPT_HASH,
                "alma_bcrypt",
                _FAKE_BCRYPT_PARAMS,
                source_vendor="alma",
                legacy_hash_created_at_source=future_anchor,
            )
        after = timezone.now()
        self.assertTrue(ok)
        user.refresh_from_db()
        # Clamped to now(), not the future value.
        self.assertGreaterEqual(
            user.legacy_hash_created_at,
            before - timedelta(seconds=1),
        )
        self.assertLessEqual(
            user.legacy_hash_created_at,
            after + timedelta(seconds=1),
        )
        # Warning log emitted; mentions the clamp event but NEVER the
        # hash bytes.
        joined = "\n".join(cm.output)
        self.assertIn("legacy_hash_intake_anchor_clamped_future", joined)
        self.assertNotIn(_FAKE_BCRYPT_HASH, joined)

    def test_near_future_within_tolerance_not_clamped(self) -> None:
        user = self._make_user("near_future")
        # 30 seconds in the future — within the 60s tolerance window;
        # should be stored as-is (not clamped).
        near_future = timezone.now() + timedelta(seconds=30)
        ok = store_legacy_hash(
            user,
            _FAKE_BCRYPT_HASH,
            "bcrypt",
            _FAKE_BCRYPT_PARAMS,
            source_vendor="blackbaud",
            legacy_hash_created_at_source=near_future,
        )
        self.assertTrue(ok)
        user.refresh_from_db()
        # Stored value matches the input (within ms).
        delta = abs(
            (user.legacy_hash_created_at - near_future).total_seconds()
        )
        self.assertLess(delta, 1.0)


class LegacyHashIntakeNoSecretsLoggedPerVendorTests(TestCase):
    """`assertLogs` proves the logger never sees hash / salt during
    per-vendor intake — extension of the v3.32.0 NoSecretsLogged pattern
    to the new anchor-coercion code path (string parse + future clamp)."""

    def test_logger_silent_on_hash_during_string_anchor_path(self) -> None:
        user = User.objects.create_user(
            username="no_secret_v3_34",
            password="dontcare",
            email="no_secret_v3_34@example.com",
        )
        anchor_iso = (timezone.now() - timedelta(days=30)).isoformat()
        with self.assertLogs(
            "apps.migration_cloud.services.legacy_hash_intake",
            level="INFO",
        ) as cm:
            ok = store_legacy_hash(
                user,
                _HASH_SENTINEL,
                "pbkdf2_sha512",
                {"iterations": 120000, "salt": _SALT_SENTINEL},
                source_vendor="powerschool",
                legacy_hash_created_at_source=anchor_iso,
            )
        self.assertTrue(ok)
        joined = "\n".join(cm.output)
        # Never log the hash bytes, never the salt.
        self.assertNotIn(_HASH_SENTINEL, joined)
        self.assertNotIn(_SALT_SENTINEL, joined)
        # But the operator-visible metadata IS logged.
        self.assertIn("pbkdf2_sha512", joined)
        self.assertIn("powerschool", joined)
        # And the new v3.34.0 string-parse flag is recorded.
        self.assertIn("legacy_hash_intake_stored", joined)

    def test_logger_silent_on_hash_during_future_clamp_path(self) -> None:
        user = User.objects.create_user(
            username="no_secret_clamp",
            password="dontcare",
            email="no_secret_clamp@example.com",
        )
        future = timezone.now() + timedelta(minutes=10)
        with self.assertLogs(
            "apps.migration_cloud.services.legacy_hash_intake",
            level="WARNING",
        ) as cm:
            ok = store_legacy_hash(
                user,
                _HASH_SENTINEL,
                "bcrypt",
                {"cost": 12, "salt": _SALT_SENTINEL},
                source_vendor="blackbaud",
                legacy_hash_created_at_source=future,
            )
        self.assertTrue(ok)
        joined = "\n".join(cm.output)
        self.assertNotIn(_HASH_SENTINEL, joined)
        self.assertNotIn(_SALT_SENTINEL, joined)
        # Clamp event IS logged.
        self.assertIn("legacy_hash_intake_anchor_clamped_future", joined)
