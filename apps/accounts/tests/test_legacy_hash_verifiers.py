"""Tests for the legacy hash verifier registry + each per-vendor module.

No DB needed — pure verifier round-trips against synthesised hashes.
All tests are :class:`SimpleTestCase` so they run in CI without a tenant
schema and without touching the User table.

Critical regression coverage:

* Each registered algorithm round-trips a known password.
* Wrong passwords reliably return ``matched=False``.
* The logger NEVER receives the password or the stored hash. This is the
  single most important invariant — credential-equivalent secrets must
  never appear in logs, error pages, or audit trails.
* Unknown algorithm slugs return ``False`` cleanly (no exception).
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import logging
import unittest
from io import StringIO

from django.test import SimpleTestCase

from apps.accounts.legacy_hashes import (
    is_supported_algorithm,
    known_algorithms,
    verify,
)
from apps.accounts.legacy_hashes.facts import FACTSAutoDetectVerifier
from apps.accounts.legacy_hashes.powerschool import (
    PowerSchoolPBKDF2SHA512Verifier,
)
from apps.accounts.legacy_hashes.skyward import SkywardAutoDetectVerifier


def _bcrypt_available() -> bool:
    try:
        importlib.import_module("bcrypt")
    except ImportError:
        try:
            importlib.import_module("passlib.hash")
        except ImportError:
            return False
    return True


BCRYPT_AVAILABLE = _bcrypt_available()


class RegistryTests(SimpleTestCase):
    def test_all_six_algorithms_registered(self):
        slugs = set(known_algorithms())
        self.assertEqual(
            slugs,
            {
                "pbkdf2_sha512",
                "bcrypt",
                "veracross_bcrypt",
                "alma_bcrypt",
                "facts_auto",
                "skyward_auto",
            },
        )

    def test_is_supported_algorithm(self):
        self.assertTrue(is_supported_algorithm("pbkdf2_sha512"))
        self.assertFalse(is_supported_algorithm("not_a_real_slug"))
        self.assertFalse(is_supported_algorithm(""))

    def test_unknown_algorithm_returns_no_match_cleanly(self):
        # Backend treats this as "no match", not as "error".
        self.assertFalse(
            verify("not_a_real_slug", {}, "irrelevant", "irrelevant")
        )


class PowerSchoolVerifierTests(SimpleTestCase):
    PASSWORD = "Correct-Horse-Battery-Staple-42"
    SALT = b"powerschool-test-salt-0001"
    ITERATIONS = 50_000

    def _synthesize(self, password: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha512",
            password.encode("utf-8"),
            self.SALT,
            self.ITERATIONS,
            dklen=64,
        ).hex()

    def test_correct_password_matches(self):
        stored = self._synthesize(self.PASSWORD)
        params = {"salt": self.SALT.hex(), "iterations": self.ITERATIONS}
        self.assertTrue(verify("pbkdf2_sha512", params, stored, self.PASSWORD))

    def test_wrong_password_does_not_match(self):
        stored = self._synthesize(self.PASSWORD)
        params = {"salt": self.SALT.hex(), "iterations": self.ITERATIONS}
        self.assertFalse(verify("pbkdf2_sha512", params, stored, "wrong"))

    def test_base64_salt_also_accepted(self):
        stored = self._synthesize(self.PASSWORD)
        params = {
            "salt": base64.b64encode(self.SALT).decode("ascii"),
            "iterations": self.ITERATIONS,
        }
        self.assertTrue(verify("pbkdf2_sha512", params, stored, self.PASSWORD))

    def test_default_iterations_when_missing(self):
        stored = self._synthesize(self.PASSWORD)  # uses 50_000 default
        params = {"salt": self.SALT.hex()}  # no iterations key
        self.assertTrue(verify("pbkdf2_sha512", params, stored, self.PASSWORD))

    def test_missing_salt_returns_no_match(self):
        verifier = PowerSchoolPBKDF2SHA512Verifier()
        result = verifier.verify(self.PASSWORD, "deadbeef", {})
        self.assertFalse(result.matched)
        self.assertEqual(result.reason, "missing_salt")


@unittest.skipUnless(BCRYPT_AVAILABLE, "bcrypt / passlib not installed")
class BcryptVendorTests(SimpleTestCase):
    """Covers Blackbaud, Veracross, Alma — all share the same bcrypt path."""

    PASSWORD = "Tr0ub4dor-and-3"

    def _synthesize(self, password: str) -> str:
        try:
            import bcrypt
            return bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt(rounds=4)
            ).decode("utf-8")
        except ImportError:
            from passlib.hash import bcrypt as passlib_bcrypt
            return passlib_bcrypt.using(rounds=4).hash(password)

    def test_blackbaud_correct_password_matches(self):
        stored = self._synthesize(self.PASSWORD)
        self.assertTrue(verify("bcrypt", {}, stored, self.PASSWORD))

    def test_blackbaud_wrong_password_does_not_match(self):
        stored = self._synthesize(self.PASSWORD)
        self.assertFalse(verify("bcrypt", {}, stored, "wrong-pw"))

    def test_veracross_uses_same_format(self):
        stored = self._synthesize(self.PASSWORD)
        self.assertTrue(verify("veracross_bcrypt", {}, stored, self.PASSWORD))
        self.assertFalse(verify("veracross_bcrypt", {}, stored, "nope"))

    def test_alma_uses_same_format(self):
        stored = self._synthesize(self.PASSWORD)
        self.assertTrue(verify("alma_bcrypt", {}, stored, self.PASSWORD))
        self.assertFalse(verify("alma_bcrypt", {}, stored, "nope"))


class FACTSAutoDetectTests(SimpleTestCase):
    PASSWORD = "FACTS-Test-Password-1"
    SALT = b"facts-salt-xyz"
    ITERATIONS = 10_000

    def test_pbkdf2_sha1_branch(self):
        derived = hashlib.pbkdf2_hmac(
            "sha1",
            self.PASSWORD.encode("utf-8"),
            self.SALT,
            self.ITERATIONS,
        )
        stored = derived.hex()
        params = {"salt": self.SALT.hex(), "iterations": self.ITERATIONS}
        self.assertTrue(verify("facts_auto", params, stored, self.PASSWORD))
        self.assertFalse(verify("facts_auto", params, stored, "wrong"))

    @unittest.skipUnless(BCRYPT_AVAILABLE, "bcrypt / passlib not installed")
    def test_bcrypt_branch(self):
        try:
            import bcrypt
            stored = bcrypt.hashpw(
                self.PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=4)
            ).decode("utf-8")
        except ImportError:
            from passlib.hash import bcrypt as passlib_bcrypt
            stored = passlib_bcrypt.using(rounds=4).hash(self.PASSWORD)
        self.assertTrue(verify("facts_auto", {}, stored, self.PASSWORD))
        self.assertFalse(verify("facts_auto", {}, stored, "wrong"))

    def test_unrecognized_format_returns_false(self):
        verifier = FACTSAutoDetectVerifier()
        result = verifier.verify(self.PASSWORD, "not-a-hash-at-all", {})
        self.assertFalse(result.matched)
        self.assertEqual(result.reason, "unrecognized_format")


class SkywardAutoDetectTests(SimpleTestCase):
    PASSWORD = "Skyward-Test-Pwd-2"
    SALT = "skyward-salt-abc"  # str — Skyward stores salt as utf-8 text

    def test_sha512_branch(self):
        digest = hashlib.sha512(
            self.SALT.encode("utf-8") + self.PASSWORD.encode("utf-8")
        ).hexdigest()
        params = {"salt": self.SALT}
        self.assertTrue(verify("skyward_auto", params, digest, self.PASSWORD))
        self.assertFalse(verify("skyward_auto", params, digest, "wrong"))

    @unittest.skipUnless(BCRYPT_AVAILABLE, "bcrypt / passlib not installed")
    def test_bcrypt_branch(self):
        try:
            import bcrypt
            stored = bcrypt.hashpw(
                self.PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=4)
            ).decode("utf-8")
        except ImportError:
            from passlib.hash import bcrypt as passlib_bcrypt
            stored = passlib_bcrypt.using(rounds=4).hash(self.PASSWORD)
        self.assertTrue(verify("skyward_auto", {}, stored, self.PASSWORD))
        self.assertFalse(verify("skyward_auto", {}, stored, "wrong"))

    def test_unrecognized_format_returns_false(self):
        verifier = SkywardAutoDetectVerifier()
        result = verifier.verify(self.PASSWORD, "not-a-real-hash", {})
        self.assertFalse(result.matched)


class NoSecretsLoggedTests(SimpleTestCase):
    """Critical: passwords + hashes + salts NEVER reach the log stream."""

    SECRET_PASSWORD = "S3cret-Should-Not-Appear"
    SECRET_SALT = b"absolutely-secret-salt-value"

    def _build_stream_handler(self) -> tuple[logging.Handler, StringIO]:
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(message)s %(user_id)s"))
        return handler, stream

    def test_no_password_or_hash_logged_on_failure(self):
        stored = hashlib.pbkdf2_hmac(
            "sha512",
            self.SECRET_PASSWORD.encode("utf-8"),
            self.SECRET_SALT,
            50_000,
            dklen=64,
        ).hex()
        params = {"salt": self.SECRET_SALT.hex(), "iterations": 50_000}

        # Attach a capturing handler to the root logger AND to the
        # legacy-hashes module logger to cover any logging path.
        captured = StringIO()
        root_logger = logging.getLogger()
        handler = logging.StreamHandler(captured)
        handler.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)
        prev_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        try:
            # Verifier path — failure case.
            self.assertFalse(
                verify("pbkdf2_sha512", params, stored, "wrong-password")
            )
            # Verifier path — success case.
            self.assertTrue(
                verify("pbkdf2_sha512", params, stored, self.SECRET_PASSWORD)
            )
        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(prev_level)

        log_text = captured.getvalue()
        self.assertNotIn(self.SECRET_PASSWORD, log_text)
        self.assertNotIn("wrong-password", log_text)
        self.assertNotIn(stored, log_text)
        self.assertNotIn(self.SECRET_SALT.hex(), log_text)
