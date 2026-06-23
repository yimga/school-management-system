"""Stdlib unittest coverage for ``verify_get_model_integrity`` (AST layer).

The runtime resolution phase needs Django (exercised in CI's django-tests
job + by the verifier's own --compare). These tests lock the pure-AST
collection layer — which calls are recognized, which literal shapes resolve,
and which guard/marker patterns excuse a call — with no Django dependency.

Covered:
  * two-arg ``get_model("app","Model")`` recognized (bare / apps. / django_apps.)
  * single dotted ``get_model("app.Model")`` recognized
  * non-literal args (f-string / variable) NOT collected
  * ``# get-model-allow:`` marker (same line / line above) excuses
  * try/except LookupError (literal + named-tuple alias) excuses
  * try/except ValueError does NOT excuse
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

import verify_get_model_integrity as v  # noqa: E402


def _calls(src: str):
    tree = ast.parse(textwrap.dedent(src))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and v._is_get_model_call(n)]


class CallRecognitionTests(unittest.TestCase):
    def test_recognizes_call_shapes(self):
        calls = _calls(
            """
            get_model("a", "B")
            apps.get_model("a", "B")
            django_apps.get_model("a", "B")
            other.method("a", "B")
            """
        )
        self.assertEqual(len(calls), 3)  # the 3 get_model variants, not other.method

    def test_two_arg_literal(self):
        (c,) = _calls('apps.get_model("evals", "Evaluation")')
        self.assertEqual(v._literal_target(c), ("evals", "Evaluation"))

    def test_single_dotted_literal(self):
        (c,) = _calls('get_model("evals.Evaluation")')
        self.assertEqual(v._literal_target(c), ("evals", "Evaluation"))

    def test_non_literal_not_resolved(self):
        (c,) = _calls('get_model(app_var, model_var)')
        self.assertIsNone(v._literal_target(c))
        (c2,) = _calls('get_model(f"{app}.{model}")')
        self.assertIsNone(v._literal_target(c2))


class ContentTypeTargetTests(unittest.TestCase):
    def _call(self, src: str):
        tree = ast.parse(textwrap.dedent(src))
        return next(n for n in ast.walk(tree) if isinstance(n, ast.Call))

    def test_literal_contenttype_lookup(self):
        c = self._call('ContentType.objects.get(app_label="siteconfig", model="sitesettings")')
        self.assertEqual(v._contenttype_target(c), ("siteconfig", "sitesettings"))

    def test_filter_shape_also_matched(self):
        c = self._call('ContentType.objects.filter(app_label="evals", model="evaluation").first()')
        # .first() is the outer call; walk finds the .filter() call too — assert filter resolves
        tree = ast.parse('ContentType.objects.filter(app_label="evals", model="evaluation")')
        inner = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        self.assertEqual(v._contenttype_target(inner), ("evals", "evaluation"))

    def test_non_contenttype_call_ignored(self):
        c = self._call('SomeModel.objects.get(app_label="x", model="y")')
        self.assertIsNone(v._contenttype_target(c))

    def test_non_literal_kwargs_ignored(self):
        c = self._call('ContentType.objects.get(app_label=app_var, model="y")')
        self.assertIsNone(v._contenttype_target(c))


class GuardMarkerTests(unittest.TestCase):
    def test_marker_excuses_same_and_above(self):
        marked = v._marked_linenos(
            [
                'get_model("a", "B")  # get-model-allow: provisioned later',  # 1
                "# get-model-allow: above",  # 2
                'get_model("a", "C")',  # 3
            ]
        )
        self.assertTrue(v._is_excused(1, set(), marked))
        self.assertTrue(v._is_excused(3, set(), marked))
        self.assertFalse(v._is_excused(9, set(), marked))

    def test_guard_lookuperror_and_named_tuple_and_negative(self):
        tree = ast.parse(
            textwrap.dedent(
                """
                _SOFT = (LookupError, ValueError)
                try:
                    a = get_model("x", "A")
                except LookupError:
                    a = None
                try:
                    b = get_model("x", "B")
                except _SOFT:
                    b = None
                try:
                    c = get_model("x", "C")
                except ValueError:
                    c = None
                """
            )
        )
        guarded = v._guarded_linenos(tree)
        self.assertIn(4, guarded)      # LookupError-guarded
        self.assertIn(8, guarded)      # named-tuple-guarded
        self.assertNotIn(12, guarded)  # ValueError-only -> not guarded

    def test_aliases_detects_lookuperror_tuple(self):
        tree = ast.parse("_SOFT = (LookupError, KeyError)\n_NO = (KeyError, ValueError)\n")
        aliases = v._exception_tuple_aliases(tree)
        self.assertIn("_SOFT", aliases)
        self.assertNotIn("_NO", aliases)


if __name__ == "__main__":
    unittest.main()
