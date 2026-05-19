"""HMAC verifier tests — round-trip + tamper + replay-window + headers."""

from __future__ import annotations

import hashlib
import hmac
import time
import unittest

from runmycampus_webhook_verifier import (
    BadSignatureError,
    ClockSkewError,
    DEFAULT_TOLERANCE_SECONDS,
    MissingHeaderError,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    UnsupportedAlgorithmError,
    VerificationError,
    canonicalize,
    compute_signature,
    verify_signature,
    verify_signature_strict,
)


SECRET = "whsec_test_NEVER_USE_IN_PRODUCTION"
PAYLOAD = {
    "event": "migration.bundle.completed",
    "delivery_id": "d_abc123",
    "tenant_id": 42,
}


def _sign(secret: str, body: bytes) -> str:
    """Test helper: HMAC the body, return the header value."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class RoundTripTests(unittest.TestCase):
    """Happy path: signed → verified."""

    def test_round_trip_simple(self):
        body = canonicalize(PAYLOAD)
        header = _sign(SECRET, body)
        self.assertTrue(verify_signature(body, header, SECRET))
        # Strict variant should NOT raise.
        verify_signature_strict(body, header, SECRET)

    def test_round_trip_with_string_body(self):
        body = canonicalize(PAYLOAD).decode("utf-8")
        header = _sign(SECRET, body.encode("utf-8"))
        self.assertTrue(verify_signature(body, header, SECRET))

    def test_round_trip_with_bytes_secret(self):
        body = canonicalize(PAYLOAD)
        secret_bytes = SECRET.encode("utf-8")
        header = _sign(SECRET, body)
        self.assertTrue(verify_signature(body, header, secret_bytes))

    def test_compute_signature_produces_valid_header(self):
        body = canonicalize(PAYLOAD)
        header = compute_signature(body, SECRET)
        self.assertTrue(header.startswith("sha256="))
        self.assertTrue(verify_signature(body, header, SECRET))


class TamperedBodyTests(unittest.TestCase):
    """Any change to the signed bytes MUST be rejected."""

    def test_body_byte_changed_rejected(self):
        body = canonicalize(PAYLOAD)
        header = _sign(SECRET, body)
        tampered = body[:-1] + b"x"  # change last byte
        self.assertFalse(verify_signature(tampered, header, SECRET))
        with self.assertRaises(BadSignatureError):
            verify_signature_strict(tampered, header, SECRET)

    def test_wrong_secret_rejected(self):
        body = canonicalize(PAYLOAD)
        header = _sign(SECRET, body)
        self.assertFalse(verify_signature(body, header, "different_secret"))
        with self.assertRaises(BadSignatureError):
            verify_signature_strict(body, header, "different_secret")

    def test_empty_body_with_old_signature_rejected(self):
        body = canonicalize(PAYLOAD)
        header = _sign(SECRET, body)
        self.assertFalse(verify_signature(b"", header, SECRET))


class HeaderContractTests(unittest.TestCase):
    """Wrong / missing / malformed signature headers."""

    def test_missing_header_returns_false(self):
        body = canonicalize(PAYLOAD)
        self.assertFalse(verify_signature(body, None, SECRET))
        with self.assertRaises(MissingHeaderError):
            verify_signature_strict(body, None, SECRET)

    def test_empty_header_returns_false(self):
        body = canonicalize(PAYLOAD)
        self.assertFalse(verify_signature(body, "", SECRET))
        with self.assertRaises(MissingHeaderError):
            verify_signature_strict(body, "", SECRET)

    def test_whitespace_header_returns_false(self):
        body = canonicalize(PAYLOAD)
        self.assertFalse(verify_signature(body, "   ", SECRET))
        with self.assertRaises(MissingHeaderError):
            verify_signature_strict(body, "   ", SECRET)

    def test_wrong_prefix_returns_false(self):
        body = canonicalize(PAYLOAD)
        # Future sha512 must not silently pass.
        bad_header = "sha512=" + hashlib.sha512(body).hexdigest()
        self.assertFalse(verify_signature(body, bad_header, SECRET))
        with self.assertRaises(UnsupportedAlgorithmError):
            verify_signature_strict(body, bad_header, SECRET)

    def test_no_prefix_returns_false(self):
        body = canonicalize(PAYLOAD)
        bare_hex = hashlib.sha256(body).hexdigest()
        self.assertFalse(verify_signature(body, bare_hex, SECRET))
        with self.assertRaises(UnsupportedAlgorithmError):
            verify_signature_strict(body, bare_hex, SECRET)

    def test_bytes_header_accepted(self):
        body = canonicalize(PAYLOAD)
        header = _sign(SECRET, body).encode("ascii")
        self.assertTrue(verify_signature(body, header, SECRET))

    def test_list_header_first_element_used(self):
        body = canonicalize(PAYLOAD)
        header = _sign(SECRET, body)
        # WSGI-style — repeated header arrives as a list.
        self.assertTrue(verify_signature(body, [header], SECRET))

    def test_constant_string_names_pinned(self):
        # Customers read these constants — if they ever change, mark it a major.
        self.assertEqual(SIGNATURE_HEADER, "X-RunMyCampus-Signature")
        self.assertEqual(TIMESTAMP_HEADER, "X-RunMyCampus-Timestamp")
        self.assertEqual(DEFAULT_TOLERANCE_SECONDS, 300)


class ClockSkewTests(unittest.TestCase):
    """Replay-defense via the timestamp header."""

    def _signed(self):
        body = canonicalize(PAYLOAD)
        header = _sign(SECRET, body)
        return body, header

    def test_no_timestamp_header_skips_skew_check(self):
        body, header = self._signed()
        # Caller omits timestamp_header — should not raise.
        self.assertTrue(verify_signature(body, header, SECRET))

    def test_in_window_timestamp_accepted(self):
        body, header = self._signed()
        now = 1_700_000_000.0
        # Signed 100s ago, default tolerance 300s → ok.
        self.assertTrue(verify_signature(
            body, header, SECRET,
            timestamp_header=str(int(now - 100)),
            now=now,
        ))

    def test_boundary_exactly_at_tolerance_accepted(self):
        body, header = self._signed()
        now = 1_700_000_000.0
        self.assertTrue(verify_signature(
            body, header, SECRET,
            timestamp_header=str(int(now - DEFAULT_TOLERANCE_SECONDS)),
            now=now,
        ))

    def test_just_outside_tolerance_rejected(self):
        body, header = self._signed()
        now = 1_700_000_000.0
        self.assertFalse(verify_signature(
            body, header, SECRET,
            timestamp_header=str(int(now - DEFAULT_TOLERANCE_SECONDS - 1)),
            now=now,
        ))
        with self.assertRaises(ClockSkewError) as ctx:
            verify_signature_strict(
                body, header, SECRET,
                timestamp_header=str(int(now - DEFAULT_TOLERANCE_SECONDS - 1)),
                now=now,
            )
        # Skew magnitude should be exposed for debugging WITHOUT
        # leaking the secret or body.
        self.assertGreater(ctx.exception.skew_seconds, DEFAULT_TOLERANCE_SECONDS)

    def test_future_timestamp_also_rejected(self):
        """Clock skew is symmetric — future timestamps must also be rejected."""
        body, header = self._signed()
        now = 1_700_000_000.0
        future_ts = str(int(now + DEFAULT_TOLERANCE_SECONDS + 10))
        with self.assertRaises(ClockSkewError):
            verify_signature_strict(
                body, header, SECRET,
                timestamp_header=future_ts,
                now=now,
            )

    def test_non_numeric_timestamp_rejected(self):
        body, header = self._signed()
        self.assertFalse(verify_signature(
            body, header, SECRET,
            timestamp_header="not-a-number",
        ))
        with self.assertRaises(MissingHeaderError):
            verify_signature_strict(
                body, header, SECRET,
                timestamp_header="not-a-number",
            )

    def test_custom_tolerance_honored(self):
        body, header = self._signed()
        now = 1_700_000_000.0
        # 50s skew, but only 30s tolerated → reject.
        self.assertFalse(verify_signature(
            body, header, SECRET,
            timestamp_header=str(int(now - 50)),
            tolerance_seconds=30,
            now=now,
        ))


class ConstantTimeCompareTests(unittest.TestCase):
    """The compare uses hmac.compare_digest — sanity-check it.

    We don't try to measure timing in unit tests (flaky), but we do
    verify the path is exercised.
    """

    def test_two_different_signatures_of_same_length_both_rejected(self):
        body = canonicalize(PAYLOAD)
        fake = "sha256=" + ("0" * 64)  # right shape, wrong bytes
        self.assertFalse(verify_signature(body, fake, SECRET))


class StandaloneVendoredParityTests(unittest.TestCase):
    """The standalone vendored file MUST produce the same output as the package.

    This guards against the deprecated copy drifting; both ship to
    customers and a divergence would silently break either path.
    """

    def test_standalone_file_signature_matches_package(self):
        # Locate the vendored file relative to this test.
        import os
        import importlib.util

        standalone = os.path.normpath(os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..",
            "apps", "migration_cloud", "api",
            "webhook_verifier_sdk.py",
        ))
        if not os.path.exists(standalone):
            self.skipTest(f"standalone file not present at {standalone}")

        spec = importlib.util.spec_from_file_location("_standalone", standalone)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        body = canonicalize(PAYLOAD)
        pkg_sig = compute_signature(body, SECRET)
        vendored_sig = mod.compute_signature(body, SECRET)
        self.assertEqual(pkg_sig, vendored_sig)


if __name__ == "__main__":
    unittest.main()
