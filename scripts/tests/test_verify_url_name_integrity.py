"""Stdlib unittest coverage for ``verify_url_name_integrity`` (AST/regex layer).

The runtime resolution phase needs Django (exercised in CI's django-tests
job + by the verifier's own --compare). These tests lock the pure
collection layer — which calls/tags are recognized, which literal shapes
resolve, and which guard/marker patterns excuse a reference — with no
Django dependency.

Covered:
  * ``reverse`` / ``reverse_lazy`` (bare / attribute) recognized; others not
  * literal first-arg extraction; non-literal (variable / f-string) ignored
  * ``{% url "x" %}`` / ``{% url 'x' %}`` regex captures the name; ``{% url var %}`` ignored
  * try/except NoReverseMatch (literal + named-tuple alias) excuses; ValueError does not
  * ``# url-name-allow:`` marker (same line / line above) excuses
"""

from __future__ import annotations

import ast
import pathlib
import sys
import textwrap
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_url_name_integrity as v  # noqa: E402


def _calls(src: str):
    tree = ast.parse(textwrap.dedent(src))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


class CallRecognitionTests(unittest.TestCase):
    def test_recognizes_reverse_shapes(self):
        calls = _calls(
            """
            reverse("a:b")
            reverse_lazy("a:b")
            urls.reverse("a:b")
            django.urls.reverse_lazy("a:b")
            other.func("a:b")
            """
        )
        recognized = [c for c in calls if v._is_reverse_call(c)]
        self.assertEqual(len(recognized), 4)  # 4 reverse variants, not other.func

    def test_literal_first_arg(self):
        (c,) = [c for c in _calls('reverse("schools:detail")') if v._is_reverse_call(c)]
        self.assertEqual(v._literal_first_arg(c), "schools:detail")

    def test_non_literal_first_arg_ignored(self):
        for src in ('reverse(name_var)', 'reverse(f"{ns}:detail")'):
            (c,) = [c for c in _calls(src) if v._is_reverse_call(c)]
            self.assertIsNone(v._literal_first_arg(c))


class TemplateRegexTests(unittest.TestCase):
    def _name(self, line: str):
        m = v._URL_TAG_RE.search(line)
        if not m:
            return None
        return m.group(2) if m.group(2) is not None else m.group(3)

    def test_double_and_single_quotes(self):
        self.assertEqual(self._name('<a href="{% url "schools:detail" obj.pk %}">'), "schools:detail")
        self.assertEqual(self._name("{% url 'portal:home' %}"), "portal:home")

    def test_variable_name_not_matched(self):
        self.assertIsNone(self._name("{% url some_var pk=1 %}"))

    def test_as_var_form(self):
        self.assertEqual(self._name('{% url "billing:invoice" inv.pk as the_url %}'), "billing:invoice")


class GuardMarkerTests(unittest.TestCase):
    def test_aliases_detects_noreversematch_tuple(self):
        tree = ast.parse("_SOFT = (NoReverseMatch, KeyError)\n_NO = (KeyError, ValueError)\n")
        aliases = v._exception_tuple_aliases(tree)
        self.assertIn("_SOFT", aliases)
        self.assertNotIn("_NO", aliases)

    def test_guard_noreversematch_and_named_tuple_and_negative(self):
        tree = ast.parse(
            textwrap.dedent(
                """
                _SOFT = (NoReverseMatch, ValueError)
                try:
                    a = reverse("x:a")
                except NoReverseMatch:
                    a = "#"
                try:
                    b = reverse("x:b")
                except _SOFT:
                    b = "#"
                try:
                    c = reverse("x:c")
                except ValueError:
                    c = "#"
                """
            )
        )
        guarded = v._guarded_linenos(tree)
        self.assertIn(4, guarded)       # NoReverseMatch-guarded
        self.assertIn(8, guarded)       # named-tuple-guarded
        self.assertNotIn(12, guarded)   # ValueError-only -> not guarded

    def test_marker_excuses_same_and_above(self):
        marked = v._marked_linenos(
            [
                'reverse("x:a")  # url-name-allow: deferred route',  # 1
                "# url-name-allow: above",  # 2
                'reverse("x:b")',  # 3
            ]
        )
        self.assertTrue(v._is_excused(1, set(), marked))
        self.assertTrue(v._is_excused(3, set(), marked))
        self.assertFalse(v._is_excused(9, set(), marked))


if __name__ == "__main__":
    unittest.main()
