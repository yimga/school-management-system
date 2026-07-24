"""Tests for the en_XA pseudo-locale QA tooling (M21/G3).

Covers the pure transform (`scripts/pseudo_locale_transform.py`), the CI gate's PO
parser + scan (`scripts/verify_pseudo_locale.py`), and the generator command.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from pseudo_locale_transform import format_tokens, pseudofy, token_preserving  # noqa: E402
import verify_pseudo_locale as gate  # noqa: E402


class PseudoTransformTests(unittest.TestCase):
    def test_preserves_printf_tokens(self):
        src = "Hello %(name)s, you have %d new messages (%.1f%%)"
        self.assertEqual(format_tokens(pseudofy(src)), format_tokens(src))
        self.assertTrue(token_preserving(src))

    def test_preserves_brace_tokens(self):
        src = "Welcome {user} to {place}, seat {0}"
        self.assertEqual(format_tokens(pseudofy(src)), format_tokens(src))

    def test_preserves_html_tokens(self):
        src = 'Click <a href="/x">here</a> to <b>continue</b>'
        self.assertEqual(format_tokens(pseudofy(src)), format_tokens(src))

    def test_percent_literal_is_a_token(self):
        self.assertIn("%%", format_tokens("50%% complete"))
        self.assertTrue(token_preserving("50%% complete"))

    def test_plain_text_is_transformed_and_wrapped(self):
        out = pseudofy("Settings")
        self.assertNotEqual(out, "Settings")
        self.assertTrue(out.startswith("⟦"))
        self.assertTrue(out.endswith("⟧"))
        # expansion padding present
        self.assertIn("·", out)

    def test_empty_stays_empty(self):
        self.assertEqual(pseudofy(""), "")

    def test_token_only_string_preserved(self):
        # A msgid that is purely a token must round-trip its token.
        self.assertEqual(format_tokens(pseudofy("%(count)s")), ["%(count)s"])


class PseudoGateScanTests(unittest.TestCase):
    _PO = (
        'msgid ""\n'
        'msgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        "\n"
        'msgid "Simple string"\n'
        'msgstr ""\n'
        "\n"
        'msgid "With %(name)s token"\n'
        'msgstr ""\n'
        "\n"
        'msgid ""\n'
        '"A multi-line "\n'
        '"continuation string"\n'
        'msgstr ""\n'
    )

    def _write_po(self, tmp: Path) -> Path:
        po = tmp / "django.po"
        po.write_text(self._PO, encoding="utf-8")
        return po

    def test_iter_skips_header_and_reads_continuations(self):
        with tempfile.TemporaryDirectory() as d:
            po = self._write_po(Path(d))
            got = list(gate.iter_source_strings(po))
        self.assertIn("Simple string", got)
        self.assertIn("With %(name)s token", got)
        self.assertIn("A multi-line continuation string", got)
        self.assertNotIn("", got)  # header entry skipped

    def test_scan_reports_zero_failures_on_clean_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            po = self._write_po(Path(d))
            result = gate.scan(po)
        self.assertEqual(result["failure_count"], 0)
        self.assertEqual(result["checked"], 3)
        self.assertEqual(result["transformed"], 3)

    def test_scan_missing_catalog_is_empty(self):
        result = gate.scan(Path(tempfile.gettempdir()) / "does-not-exist-abc.po")
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["failure_count"], 0)


class GeneratePseudoLocaleCommandTests(TestCase):
    def test_check_mode_runs_without_writing(self):
        # --check reads the real locale/en catalog and reports without touching disk.
        from django.conf import settings

        dest = Path(settings.BASE_DIR) / "locale" / "en_XA"
        existed = dest.exists()
        call_command("generate_pseudo_locale", "--check", verbosity=0)
        if not existed:
            self.assertFalse(dest.exists(), "check mode must not create the catalog dir")


if __name__ == "__main__":
    unittest.main()
