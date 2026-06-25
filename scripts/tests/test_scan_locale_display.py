"""Stdlib unittest coverage for ``scan_locale_display``.

Locks the locale-display gate that forbids a hardcoded currency symbol glued to
an interpolated value (bypassing the locale-aware ``|format_currency`` filter /
``platform_currency_symbol()`` helper). Exercises the Python f-string detector,
the Django-template detector, the allow-marker escape, and the false-positive
guards (JS template literals, mid-string symbols, plain numbers).
"""

from __future__ import annotations

import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scan_locale_display as s  # noqa: E402


class PythonDetectorTests(unittest.TestCase):
    def _scan(self, src: str):
        return s._scan_python_text("apps/x/foo.py", src)

    def test_flags_dollar_glued_fstring(self):
        out = self._scan('def f(amount):\n    return f"${amount}"\n')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["line"], 2)

    def test_flags_dollar_with_format_spec(self):
        out = self._scan('def f(total):\n    return f"${total:,.2f}"\n')
        self.assertEqual(len(out), 1)

    def test_flags_non_dollar_symbol(self):
        out = self._scan('def f(v):\n    return f"₦{v:.0f}"\n')  # NGN
        self.assertEqual(len(out), 1)

    def test_flags_symbol_after_text_prefix(self):
        out = self._scan('def f(v, label):\n    return f"{label}: ${v}"\n')
        self.assertEqual(len(out), 1)

    def test_one_finding_per_fstring(self):
        out = self._scan('def f(a, b):\n    return f"${a} and ${b}"\n')
        self.assertEqual(len(out), 1)

    def test_plain_number_not_flagged(self):
        out = self._scan('def f(v):\n    return f"value is {v}"\n')
        self.assertEqual(out, [])

    def test_mid_string_dollar_not_flagged(self):
        # A literal "$5" with no interpolation right after the symbol is fine.
        out = self._scan('def f():\n    return f"costs $5 flat {x}"\n')
        self.assertEqual(out, [])

    def test_non_fstring_dollar_not_flagged(self):
        out = self._scan('x = "${not an fstring}"\n')
        self.assertEqual(out, [])

    def test_allow_marker_same_line_suppresses(self):
        src = 'def f(v):\n    return f"${v}"  # locale-display-allow: usd-only-internal\n'
        self.assertEqual(self._scan(src), [])

    def test_allow_marker_line_above_suppresses(self):
        src = (
            "def f(v):\n"
            "    # locale-display-allow: usd-only-internal\n"
            '    return f"${v}"\n'
        )
        self.assertEqual(self._scan(src), [])

    def test_syntax_error_is_swallowed(self):
        self.assertEqual(self._scan("def (:\n"), [])


class PrintfAndFormatDetectorTests(unittest.TestCase):
    def _scan(self, src: str):
        return s._scan_python_text("apps/x/foo.py", src)

    def test_flags_printf_dollar(self):
        out = self._scan('def f(v):\n    return "$%.2f" % v\n')
        self.assertEqual(len(out), 1)

    def test_flags_printf_thousands_suffix(self):
        out = self._scan('def f(v):\n    return "$%.1fk" % (v / 1000)\n')
        self.assertEqual(len(out), 1)

    def test_flags_printf_non_dollar_symbol(self):
        out = self._scan('def f(q):\n    return "₦%d" % q\n')  # NGN
        self.assertEqual(len(out), 1)

    def test_flags_format_method(self):
        out = self._scan('def f(v):\n    return "${}".format(v)\n')
        self.assertEqual(len(out), 1)

    def test_flags_format_method_with_spec(self):
        out = self._scan('def f(v):\n    return "${:,.2f}".format(v)\n')
        self.assertEqual(len(out), 1)

    def test_shell_var_literal_not_flagged(self):
        # "${HOME}" is not a % op nor a .format receiver — never money.
        out = self._scan('def f():\n    path = "${HOME}/x"\n    return path\n')
        self.assertEqual(out, [])

    def test_printf_without_symbol_not_flagged(self):
        out = self._scan('def f(v):\n    return "%.2f" % v\n')
        self.assertEqual(out, [])

    def test_percent_without_conversion_not_flagged(self):
        out = self._scan('def f():\n    return "rate $5" % ()\n')
        self.assertEqual(out, [])

    def test_format_on_non_money_not_flagged(self):
        out = self._scan('def f(v):\n    return "value {}".format(v)\n')
        self.assertEqual(out, [])

    def test_printf_allow_marker_suppresses(self):
        src = 'def f(v):\n    return "$%.2f" % v  # locale-display-allow: usd-internal\n'
        self.assertEqual(self._scan(src), [])


class HtmlDetectorTests(unittest.TestCase):
    def _scan(self, src: str):
        return s._scan_html_text("templates/x.html", src)

    def test_flags_dollar_django_var(self):
        out = self._scan('<div>${{ invoice.total }}</div>\n')
        self.assertEqual(len(out), 1)

    def test_flags_symbol_with_space(self):
        out = self._scan('<div>₦ {{ total }}</div>\n')  # NGN + space
        self.assertEqual(len(out), 1)

    def test_js_template_literal_not_flagged(self):
        # JS uses a single brace ${expr}; the gate requires Django's {{ .
        out = self._scan("<script>const x = `${price}`;</script>\n")
        self.assertEqual(out, [])

    def test_plain_django_var_not_flagged(self):
        out = self._scan("<div>{{ amount|format_currency }}</div>\n")
        self.assertEqual(out, [])

    def test_allow_marker_suppresses(self):
        out = self._scan(
            "<!-- locale-display-allow: marketing-usd-hero -->\n"
            "<div>${{ price }}</div>\n"
        )
        self.assertEqual(out, [])


class ContractTests(unittest.TestCase):
    def test_baseline_path_and_marker_shape(self):
        self.assertTrue(str(s.BASELINE_PATH).endswith("locale-display.json"))
        self.assertEqual(s.ALLOW_MARKER, "locale-display-allow:")

    def test_live_tree_is_clean(self):
        # The gate ships at baseline 0 — the real tree must currently be clean.
        self.assertEqual(s.scan(), [])


if __name__ == "__main__":
    unittest.main()
