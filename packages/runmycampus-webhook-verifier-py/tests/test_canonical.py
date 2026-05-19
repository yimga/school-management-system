"""Canonical-JSON serializer tests + JS-parity fixture verification."""

from __future__ import annotations

import hashlib
import json
import math
import os
import unittest

from runmycampus_webhook_verifier._canonical import (
    CanonicalJSONError,
    canonical_sha256_hex,
    canonicalize,
)


FIXTURE_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "runmycampus-webhook-verifier-js",
        "test",
        "fixtures",
        "canonical-cases.json",
    )
)


class CanonicalDeterminismTests(unittest.TestCase):
    """Same input → same bytes; dict ordering is irrelevant."""

    def test_empty_object(self):
        self.assertEqual(canonicalize({}), b"{}")

    def test_empty_array(self):
        self.assertEqual(canonicalize([]), b"[]")

    def test_key_order_independent(self):
        a = {"b": 2, "a": 1, "c": 3}
        b = {"c": 3, "a": 1, "b": 2}
        self.assertEqual(canonicalize(a), canonicalize(b))
        self.assertEqual(canonicalize(a), b'{"a":1,"b":2,"c":3}')

    def test_nested_object_keys_sorted_recursively(self):
        v = {"outer": {"z": 26, "a": 1}, "first": "value"}
        self.assertEqual(
            canonicalize(v),
            b'{"first":"value","outer":{"a":1,"z":26}}',
        )

    def test_no_whitespace(self):
        v = {"a": [1, 2, {"nested": "yes"}]}
        out = canonicalize(v).decode("utf-8")
        self.assertNotIn(" ", out)
        self.assertNotIn("\n", out)
        self.assertNotIn("\t", out)

    def test_unicode_emitted_literally_not_escaped(self):
        v = "学校管理"
        out = canonicalize(v)
        # NOT \uXXXX escaped:
        self.assertNotIn(b"\\u", out)
        # And byte-form round-trips:
        self.assertEqual(json.loads(out.decode("utf-8")), v)

    def test_escaped_control_chars(self):
        v = 'line1\nline2\t"q"\\b'
        out = canonicalize(v).decode("utf-8")
        # Newline / tab / quote / backslash MUST be escaped per JSON.
        self.assertIn("\\n", out)
        self.assertIn("\\t", out)
        self.assertIn('\\"', out)
        self.assertIn("\\\\", out)


class CanonicalRejectionTests(unittest.TestCase):
    """Non-finite floats / unsupported types are refused, not coerced."""

    def test_nan_rejected(self):
        with self.assertRaises(CanonicalJSONError):
            canonicalize(float("nan"))

    def test_inf_rejected(self):
        with self.assertRaises(CanonicalJSONError):
            canonicalize(float("inf"))

    def test_negative_inf_rejected(self):
        with self.assertRaises(CanonicalJSONError):
            canonicalize(float("-inf"))

    def test_nested_nan_rejected(self):
        with self.assertRaises(CanonicalJSONError):
            canonicalize({"x": [1, 2, math.nan]})

    def test_unsupported_type_rejected(self):
        class Custom:
            pass
        with self.assertRaises(CanonicalJSONError):
            canonicalize({"x": Custom()})


class FixtureParityTests(unittest.TestCase):
    """Read the shared JS fixture file; assert Python output matches expected bytes + SHA-256.

    If this test fails, the Python and JS twins have drifted and
    customers will see signature mismatches that look like tampering.
    """

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            cls.fixture = json.load(f)

    def test_fixture_file_exists(self):
        self.assertTrue(os.path.exists(FIXTURE_PATH))

    def test_fixture_has_cases(self):
        cases = self.fixture.get("cases", [])
        self.assertGreaterEqual(len(cases), 12,
            "fixture should cover at least 12 distinct shapes")

    def test_every_case_canonical_bytes_match(self):
        failures = []
        for case in self.fixture["cases"]:
            name = case["name"]
            expected_canon = case["expected_canonical"]
            actual_canon = canonicalize(case["input"]).decode("utf-8")
            if actual_canon != expected_canon:
                failures.append((name, expected_canon, actual_canon))
        self.assertEqual(failures, [], f"canonical-byte drift: {failures}")

    def test_every_case_sha256_matches(self):
        failures = []
        for case in self.fixture["cases"]:
            name = case["name"]
            expected_hash = case["expected_sha256"]
            actual_hash = canonical_sha256_hex(case["input"])
            if actual_hash != expected_hash:
                failures.append((name, expected_hash, actual_hash))
        self.assertEqual(failures, [], f"sha256 drift: {failures}")


if __name__ == "__main__":
    unittest.main()
