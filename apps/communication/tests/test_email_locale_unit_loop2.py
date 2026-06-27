"""No-DB unit coverage for `apps.communication.email_locale` (Testing #16, loop 2).

``normalize_locale`` is the pure normalisation primitive every email/SMS locale
fallback relies on, yet has no dedicated test in the communication suite. This
file pins its contract (region/script stripping, casing, falsy handling) plus the
``LocalizedEmail`` dataclass shape and the shipped-locale advisory constants.

Brand-new file; no edits to existing tests or source.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.communication.email_locale import (
    DEFAULT_EMAIL_LOCALE,
    SUPPORTED_EMAIL_LOCALES,
    LocalizedEmail,
    normalize_locale,
)


class NormalizeLocaleTests(SimpleTestCase):
    def test_strips_region_with_hyphen(self):
        self.assertEqual(normalize_locale("fr-CA"), "fr")

    def test_strips_region_with_underscore(self):
        self.assertEqual(normalize_locale("fr_CA"), "fr")

    def test_lowercases_bare_code(self):
        self.assertEqual(normalize_locale("FR"), "fr")

    def test_lowercases_and_strips_region(self):
        self.assertEqual(normalize_locale("PT_BR"), "pt")

    def test_trims_surrounding_whitespace(self):
        self.assertEqual(normalize_locale("  es  "), "es")

    def test_blank_returns_empty(self):
        self.assertEqual(normalize_locale("   "), "")

    def test_none_returns_empty(self):
        self.assertEqual(normalize_locale(None), "")

    def test_already_bare_code_is_unchanged(self):
        self.assertEqual(normalize_locale("en"), "en")

    def test_hyphen_takes_precedence_then_underscore(self):
        # Only the first segment before the first separator survives.
        self.assertEqual(normalize_locale("zh-Hans_CN"), "zh")


class LocalizedEmailDataclassTests(SimpleTestCase):
    def test_fields_round_trip(self):
        msg = LocalizedEmail(text="hello", html="<p>hello</p>", locale="fr")
        self.assertEqual(msg.text, "hello")
        self.assertEqual(msg.html, "<p>hello</p>")
        self.assertEqual(msg.locale, "fr")

    def test_is_frozen(self):
        msg = LocalizedEmail(text="x", html="y", locale="en")
        with self.assertRaises(Exception):
            msg.text = "mutated"  # frozen dataclass -> FrozenInstanceError


class EmailLocaleConstantsTests(SimpleTestCase):
    def test_default_locale_is_english(self):
        self.assertEqual(DEFAULT_EMAIL_LOCALE, "en")

    def test_default_is_in_supported_set(self):
        self.assertIn(DEFAULT_EMAIL_LOCALE, SUPPORTED_EMAIL_LOCALES)

    def test_supported_locales_are_bare_codes(self):
        # Advisory set should already be normalised (no region suffixes).
        for code in SUPPORTED_EMAIL_LOCALES:
            self.assertEqual(normalize_locale(code), code)
