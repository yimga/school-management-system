"""Unit tests for playbook preflight override reason normalization (no DB)."""

from django.test import SimpleTestCase

from apps.automation.playbook_override_reason import normalize_playbook_override_reason


class PlaybookOverrideReasonNormalizeTests(SimpleTestCase):
    def test_none_and_empty(self):
        self.assertEqual(normalize_playbook_override_reason(None), "")
        self.assertEqual(normalize_playbook_override_reason(""), "")

    def test_invisible_only_returns_empty(self):
        self.assertEqual(
            normalize_playbook_override_reason("\u200b\u200c\u200d\ufeff"), ""
        )
        self.assertEqual(normalize_playbook_override_reason("\u2060"), "")

    def test_strips_invisible_between_words(self):
        self.assertEqual(
            normalize_playbook_override_reason("Ops\u200bapproved"),
            "Opsapproved",
        )

    def test_preserves_real_attestation(self):
        self.assertEqual(
            normalize_playbook_override_reason("  Operator validated CSV.  "),
            "Operator validated CSV.",
        )

    def test_caps_at_400_chars(self):
        long_s = "a" * 500
        out = normalize_playbook_override_reason(long_s)
        self.assertEqual(len(out), 400)
