"""Stdlib unittest coverage for ``verify_template_reference_integrity`` (AST layer).

The runtime resolution phase needs Django (exercised in CI's django-tests job +
by the verifier's own --compare). These tests lock the pure-AST collection layer
— which calls / assignments are recognized, which literal shapes resolve, the
single-vs-list ("any") fallback semantics, the template-ish filter, and which
guard/marker patterns excuse a site — with no Django dependency.
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

import verify_template_reference_integrity as v  # noqa: E402


def _call(src: str) -> ast.Call:
    tree = ast.parse(textwrap.dedent(src))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.Call))


def _assign(src: str) -> ast.Assign:
    tree = ast.parse(textwrap.dedent(src))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.Assign))


class TemplateishTests(unittest.TestCase):
    def test_accepts_path_like(self):
        for ok in ("student/home.html", "x.txt", "a/b/c.html", "email/note.xml", "f.svg"):
            self.assertTrue(v._looks_like_template(ok), ok)

    def test_rejects_non_template(self):
        for bad in ("", "hello world", "just text", "no extension", "a b.html", "trailing/"):
            self.assertFalse(v._looks_like_template(bad), bad)


class CallCollectionTests(unittest.TestCase):
    def test_render_shortcut_positional(self):
        got = v._collect_from_call(_call('render(request, "student/home.html", ctx)'))
        self.assertEqual(got, (["student/home.html"], "single"))

    def test_render_shortcut_kwarg(self):
        got = v._collect_from_call(_call('render(request, template_name="x/y.html")'))
        self.assertEqual(got, (["x/y.html"], "single"))

    def test_render_non_request_first_arg_ignored(self):
        # custom obj.render("x.html") must NOT be read as a Django render
        self.assertIsNone(v._collect_from_call(_call('serializer.render(obj, "x.html")')))
        self.assertIsNone(v._collect_from_call(_call('render(form, "x.html")')))

    def test_render_to_string_first_positional(self):
        got = v._collect_from_call(_call('render_to_string("emails/welcome.txt", ctx)'))
        self.assertEqual(got, (["emails/welcome.txt"], "single"))

    def test_get_template(self):
        got = v._collect_from_call(_call('get_template("partials/card.html")'))
        self.assertEqual(got, (["partials/card.html"], "single"))

    def test_select_template_list_is_any_mode(self):
        got = v._collect_from_call(_call('select_template(["a.html", "b.html"])'))
        self.assertEqual(got, (["a.html", "b.html"], "any"))

    def test_template_response_second_positional(self):
        got = v._collect_from_call(_call('TemplateResponse(request, "report.html", ctx)'))
        self.assertEqual(got, (["report.html"], "single"))

    def test_non_literal_not_collected(self):
        self.assertIsNone(v._collect_from_call(_call('render(request, tpl_var, ctx)')))
        self.assertIsNone(v._collect_from_call(_call('render(request, f"{x}.html", ctx)')))

    def test_non_template_string_not_collected(self):
        # a string arg that isn't path-like (e.g. a status message) is ignored
        self.assertIsNone(v._collect_from_call(_call('render(request, "ok", ctx)')))

    def test_unrelated_call_ignored(self):
        self.assertIsNone(v._collect_from_call(_call('json.dumps("x.html")')))


class AssignCollectionTests(unittest.TestCase):
    def test_template_name_attr(self):
        got = v._collect_from_assign(_assign('template_name = "dash/home.html"'))
        self.assertEqual(got, (["dash/home.html"], "single"))

    def test_template_names_list_attr(self):
        got = v._collect_from_assign(_assign('template_names = ["a.html", "b.html"]'))
        self.assertEqual(got, (["a.html", "b.html"], "any"))

    def test_unrelated_assign_ignored(self):
        self.assertIsNone(v._collect_from_assign(_assign('title = "home.html"')))


class GuardMarkerTests(unittest.TestCase):
    def test_marker_excuses_same_and_above(self):
        marked = v._marked_linenos(
            [
                'render(request, "x.html")  # template-ref-allow: dynamic in prod',  # 1
                "# template-ref-allow: above",  # 2
                'render(request, "y.html")',  # 3
            ]
        )
        self.assertTrue(v._is_excused(1, set(), marked))
        self.assertTrue(v._is_excused(3, set(), marked))
        self.assertFalse(v._is_excused(9, set(), marked))

    def test_guard_templatedoesnotexist_and_named_tuple_and_negative(self):
        tree = ast.parse(
            textwrap.dedent(
                """
                _SOFT = (TemplateDoesNotExist, ValueError)
                try:
                    a = render(request, "x.html")
                except TemplateDoesNotExist:
                    a = None
                try:
                    b = render(request, "y.html")
                except _SOFT:
                    b = None
                try:
                    c = render(request, "z.html")
                except ValueError:
                    c = None
                """
            )
        )
        guarded = v._guarded_linenos(tree)
        self.assertIn(4, guarded)      # TemplateDoesNotExist-guarded
        self.assertIn(8, guarded)      # named-tuple-guarded
        self.assertNotIn(12, guarded)  # ValueError-only -> not guarded

    def test_aliases_detects_templatedoesnotexist_tuple(self):
        tree = ast.parse("_SOFT = (TemplateDoesNotExist, KeyError)\n_NO = (KeyError, ValueError)\n")
        aliases = v._exception_tuple_aliases(tree)
        self.assertIn("_SOFT", aliases)
        self.assertNotIn("_NO", aliases)


if __name__ == "__main__":
    unittest.main()
