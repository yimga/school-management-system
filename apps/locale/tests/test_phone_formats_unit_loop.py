"""Unit tests for the pure per-country phone placeholder / dial-code lookup.

No DB access: ``apps.locale.phone_formats`` is a plain dict + two pure
string functions. These assertions lock the fallback contract (unknown /
empty / None inputs), case-insensitivity, whitespace stripping, and the
exact published placeholder/dial-code for a representative spread of
corridors. The module previously had zero direct test coverage.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.locale.phone_formats import (
    DEFAULT_DIAL_CODE,
    DEFAULT_PLACEHOLDER,
    PHONE_FORMATS,
    dial_code,
    phone_placeholder,
)


class PhonePlaceholderTests(SimpleTestCase):
    def test_known_country_returns_published_placeholder(self):
        self.assertEqual(phone_placeholder("CM"), "+237 6XX XXX XXX")
        self.assertEqual(phone_placeholder("NG"), "+234 8XX XXX XXXX")
        self.assertEqual(phone_placeholder("US"), "+1 (XXX) XXX-XXXX")

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(phone_placeholder("ng"), phone_placeholder("NG"))
        self.assertEqual(phone_placeholder("gB"), "+44 7XXX XXXXXX")

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(phone_placeholder("  ke  "), "+254 7XX XXX XXX")

    def test_unknown_country_falls_back_to_neutral_placeholder(self):
        self.assertEqual(phone_placeholder("ZZ"), DEFAULT_PLACEHOLDER)

    def test_empty_and_none_fall_back_to_neutral_placeholder(self):
        self.assertEqual(phone_placeholder(""), DEFAULT_PLACEHOLDER)
        self.assertEqual(phone_placeholder("   "), DEFAULT_PLACEHOLDER)
        self.assertEqual(phone_placeholder(None), DEFAULT_PLACEHOLDER)


class DialCodeTests(SimpleTestCase):
    def test_known_country_returns_dial_code(self):
        self.assertEqual(dial_code("CM"), "+237")
        self.assertEqual(dial_code("ZA"), "+27")
        self.assertEqual(dial_code("IN"), "+91")

    def test_lookup_is_case_insensitive_and_stripped(self):
        self.assertEqual(dial_code(" fr "), "+33")

    def test_unknown_country_returns_empty_dial_code(self):
        # Unknown code => the tuple's first element is DEFAULT_DIAL_CODE ("").
        self.assertEqual(dial_code("ZZ"), DEFAULT_DIAL_CODE)
        self.assertEqual(dial_code("ZZ"), "")

    def test_empty_and_none_return_empty_dial_code(self):
        self.assertEqual(dial_code(""), DEFAULT_DIAL_CODE)
        self.assertEqual(dial_code(None), DEFAULT_DIAL_CODE)


class PhoneFormatsTableInvariantTests(SimpleTestCase):
    def test_every_entry_is_a_dial_code_placeholder_pair(self):
        for iso2, value in PHONE_FORMATS.items():
            self.assertEqual(len(iso2), 2, iso2)
            self.assertEqual(iso2, iso2.upper(), iso2)
            self.assertIsInstance(value, tuple)
            self.assertEqual(len(value), 2, iso2)

    def test_dial_code_and_placeholder_functions_agree_with_table(self):
        for iso2, (code, placeholder) in PHONE_FORMATS.items():
            self.assertEqual(dial_code(iso2), code, iso2)
            self.assertEqual(phone_placeholder(iso2), placeholder, iso2)

    def test_every_dial_code_starts_with_plus(self):
        for iso2, (code, _placeholder) in PHONE_FORMATS.items():
            self.assertTrue(code.startswith("+"), iso2)
