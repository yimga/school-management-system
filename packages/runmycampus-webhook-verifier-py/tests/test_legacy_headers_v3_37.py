"""v3.37.0 — packaged Python SDK ``verify(headers, ..., accept_legacy=...)`` tests.

Four tests covering the dual header family `verify` API contract:

1. New header family verifies and reports ``used_legacy_header_family=False``.
2. Legacy header family verifies and reports
   ``used_legacy_header_family=True`` when ``accept_legacy=True`` (default).
3. Legacy header family is REJECTED when ``accept_legacy=False`` and the
   result carries a non-sensitive ``reason="legacy-rejected"`` category.
4. Mixed headers (both families present) prefer the NEW family — the
   legacy header is never consulted when the canonical one is set.

All comparisons in the SDK use :func:`hmac.compare_digest`; the tests
themselves call the public API and never reach into module internals.
"""

from __future__ import annotations

import hashlib
import hmac
import unittest

from runmycampus_webhook_verifier import (
    LEGACY_SIGNATURE_HEADER,
    LEGACY_TIMESTAMP_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    VerifyResult,
    canonicalize,
    verify,
)


SECRET = "whsec_test_v3_37_NEVER_USE_IN_PRODUCTION"
PAYLOAD = {
    "event": "migration.bundle.completed",
    "delivery_id": "d_v3_37_xyz",
    "tenant_id": 7,
}


def _sig(body: bytes, secret: str = SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class VerifyDualHeaderFamilyTests(unittest.TestCase):
    """v3.37.0 — ``verify(headers, body, secret, *, accept_legacy=)`` contract."""

    def setUp(self) -> None:
        self.body = canonicalize(PAYLOAD)
        self.signature = _sig(self.body)

    # 1) New family verifies; used_legacy_header_family stays False
    def test_new_header_family_verifies_and_flags_legacy_false(self) -> None:
        headers = {SIGNATURE_HEADER: self.signature}
        result = verify(headers, self.body, SECRET)
        self.assertIsInstance(result, VerifyResult)
        self.assertTrue(result.valid)
        self.assertFalse(result.used_legacy_header_family)
        self.assertEqual(result.signature_header_name, SIGNATURE_HEADER)
        self.assertEqual(result.reason, "")

    # 2) Legacy family verifies when accept_legacy=True (default)
    def test_legacy_family_verifies_when_accept_legacy_true(self) -> None:
        headers = {LEGACY_SIGNATURE_HEADER: self.signature}
        result = verify(headers, self.body, SECRET, accept_legacy=True)
        self.assertTrue(result.valid)
        self.assertTrue(result.used_legacy_header_family)
        self.assertEqual(result.signature_header_name, LEGACY_SIGNATURE_HEADER)
        self.assertEqual(result.reason, "")
        # Default value behaves the same.
        result_default = verify(headers, self.body, SECRET)
        self.assertTrue(result_default.valid)
        self.assertTrue(result_default.used_legacy_header_family)

    # 3) Legacy family rejected when accept_legacy=False — reason is
    #    non-sensitive ``legacy-rejected``; signature bytes never echoed.
    def test_legacy_family_rejected_when_accept_legacy_false(self) -> None:
        headers = {LEGACY_SIGNATURE_HEADER: self.signature}
        result = verify(headers, self.body, SECRET, accept_legacy=False)
        self.assertFalse(result.valid)
        self.assertTrue(result.used_legacy_header_family)
        self.assertEqual(result.signature_header_name, LEGACY_SIGNATURE_HEADER)
        self.assertEqual(result.reason, "legacy-rejected")
        # ``reason`` must not contain the secret or signature digest bytes.
        self.assertNotIn(SECRET, result.reason)
        self.assertNotIn(self.signature, result.reason)

    # 4) Mixed headers — new family preferred even when legacy is set
    #    to a value that would NOT match. If the new is preferred, the
    #    legacy mismatch must NOT cause the verifier to fall through.
    def test_mixed_headers_prefer_new_family(self) -> None:
        ts = "1715990400"
        headers = {
            SIGNATURE_HEADER: self.signature,
            LEGACY_SIGNATURE_HEADER: "sha256=" + ("0" * 64),  # bogus
            TIMESTAMP_HEADER: ts,
            LEGACY_TIMESTAMP_HEADER: ts,
        }
        # ``now=`` pinned to the same instant the headers claim so the
        # clock-skew window has nothing to complain about — this test is
        # specifically asserting the preference order, not skew behavior.
        result = verify(
            headers, self.body, SECRET, accept_legacy=True, now=float(ts),
        )
        self.assertTrue(result.valid)
        self.assertFalse(
            result.used_legacy_header_family,
            "verifier must prefer the new family even when legacy is also present",
        )
        self.assertEqual(result.signature_header_name, SIGNATURE_HEADER)
        # Constant-time compare: the bogus legacy value must NOT leak in
        # reason / signature_header_name (defensive — empty reason on
        # success guarantees this; we assert it explicitly anyway).
        self.assertEqual(result.reason, "")

    def test_plain_mapping_lookup_is_fully_case_insensitive(self) -> None:
        headers = {"x-RuNmYcAmPuS-sIgNaTuRe": self.signature}
        result = verify(headers, self.body, SECRET)
        self.assertTrue(result.valid)
        self.assertFalse(result.used_legacy_header_family)
        self.assertEqual(result.signature_header_name, SIGNATURE_HEADER)

    def test_empty_canonical_signature_falls_back_to_legacy_when_accepted(self) -> None:
        headers = {
            SIGNATURE_HEADER: "   ",
            LEGACY_SIGNATURE_HEADER: self.signature,
        }
        result = verify(headers, self.body, SECRET)
        self.assertTrue(result.valid)
        self.assertTrue(result.used_legacy_header_family)
        self.assertEqual(result.signature_header_name, LEGACY_SIGNATURE_HEADER)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
