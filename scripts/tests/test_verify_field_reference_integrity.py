"""Stdlib unit tests for the AST/guard/marker layer of
``verify_field_reference_integrity`` (no Django required).

Companion to ``test_verify_relation_path_integrity.py``: that one locks the
relation gate (``select_related`` / ``prefetch_related``); this one locks the
*scalar field* gate. The runtime ``_meta.get_field`` resolution is exercised live
in ``ci.yml::django-tests`` — here we pin the static collection that decides WHICH
calls become targets and which are excused, across every member of
``_FIELD_METHODS`` (``order_by`` / ``values`` / ``values_list`` / ``only`` /
``defer`` / ``distinct``).
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "verify_field_reference_integrity.py"
_spec = importlib.util.spec_from_file_location("verify_field_reference_integrity", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["verify_field_reference_integrity"] = mod
_spec.loader.exec_module(mod)


def _call(src: str) -> ast.Call:
    """First Call node whose attr is a field method in a snippet."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in mod._FIELD_METHODS
        ):
            return node
    raise AssertionError("no field-method call found")


class FieldMethodsContractTests(unittest.TestCase):
    """The set of field-naming methods is the v1 contract — lock it exactly."""

    def test_field_methods_exact_set(self):
        self.assertEqual(
            mod._FIELD_METHODS,
            {"order_by", "values", "values_list", "only", "defer", "distinct"},
        )

    def test_filter_and_exclude_not_in_scope(self):
        # filter/exclude/get use kwargs + __ lookups — intentionally OUT of v1.
        self.assertNotIn("filter", mod._FIELD_METHODS)
        self.assertNotIn("exclude", mod._FIELD_METHODS)
        self.assertNotIn("get", mod._FIELD_METHODS)

    def test_relation_methods_not_in_scope(self):
        # select_related/prefetch_related are the relation gate's job (gate #8).
        self.assertNotIn("select_related", mod._FIELD_METHODS)
        self.assertNotIn("prefetch_related", mod._FIELD_METHODS)


class ResolveModelHeadTests(unittest.TestCase):
    def test_direct_objects_head(self):
        c = _call('StudentProfile.objects.only("external_id")')
        self.assertEqual(mod._resolve_model_head(c.func.value), "StudentProfile")

    def test_head_through_filter(self):
        c = _call('StudentProfile.objects.filter(x=1).only("a")')
        self.assertEqual(mod._resolve_model_head(c.func.value), "StudentProfile")

    def test_head_through_multiple_qs_methods(self):
        c = _call('Evaluation.objects.filter(x=1).exclude(y=2).order_by("a")')
        self.assertEqual(mod._resolve_model_head(c.func.value), "Evaluation")

    def test_lowercase_head_skipped(self):
        # `qs` is not a Capitalised model class name.
        c = _call('qs.objects.only("a")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_non_objects_head_skipped(self):
        c = _call('self.get_queryset().order_by("a")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_annotate_in_chain_skipped(self):
        # annotate introduces a pseudo-field a later order_by may legitimately name.
        c = _call('Evaluation.objects.annotate(n=Count("x")).order_by("n")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_alias_in_chain_skipped(self):
        c = _call('Evaluation.objects.alias(n=Count("x")).values("n")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_union_in_chain_skipped(self):
        c = _call('Evaluation.objects.union(other).order_by("a")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_extra_in_chain_skipped(self):
        c = _call('Evaluation.objects.extra(select={"n": "1"}).values("n")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))


class FieldLiteralsTests(unittest.TestCase):
    def test_multiple_positional(self):
        c = _call('M.objects.values("a", "b")')
        self.assertEqual(mod._field_literals(c), ["a", "b"])

    def test_first_segment_only(self):
        # related-traversal / transform tail is on another model — only head checked.
        c = _call('M.objects.order_by("author__name")')
        self.assertEqual(mod._field_literals(c), ["author"])

    def test_lookup_tail_first_segment_only(self):
        c = _call('M.objects.order_by("created__year")')
        self.assertEqual(mod._field_literals(c), ["created"])

    def test_leading_minus_stripped(self):
        # order_by("-created") descends on the `created` field.
        c = _call('M.objects.order_by("-created")')
        self.assertEqual(mod._field_literals(c), ["created"])

    def test_leading_minus_with_segment(self):
        c = _call('M.objects.order_by("-author__name")')
        self.assertEqual(mod._field_literals(c), ["author"])

    def test_pk_skipped(self):
        c = _call('M.objects.only("pk")')
        self.assertEqual(mod._field_literals(c), [])

    def test_random_order_sentinel_skipped(self):
        c = _call('M.objects.order_by("?")')
        self.assertEqual(mod._field_literals(c), [])

    def test_empty_string_skipped(self):
        c = _call('M.objects.values("")')
        self.assertEqual(mod._field_literals(c), [])

    def test_non_constant_args_ignored(self):
        # F() / variable args are not string Constants -> not field literals.
        c = _call('M.objects.order_by(F("a").desc(), some_var)')
        self.assertEqual(mod._field_literals(c), [])

    def test_whitespace_stripped(self):
        c = _call('M.objects.values("  name  ")')
        self.assertEqual(mod._field_literals(c), ["name"])


class GuardAndMarkerTests(unittest.TestCase):
    def test_try_except_fielderror_guards(self):
        src = (
            "try:\n"
            '    StudentProfile.objects.only("bogus")\n'
            "except FieldError:\n"
            "    pass\n"
        )
        guarded = mod._guarded_linenos(ast.parse(src))
        self.assertIn(2, guarded)

    def test_try_except_field_does_not_exist_guards(self):
        src = (
            "try:\n"
            '    StudentProfile.objects.values("bogus")\n'
            "except FieldDoesNotExist:\n"
            "    pass\n"
        )
        guarded = mod._guarded_linenos(ast.parse(src))
        self.assertIn(2, guarded)

    def test_bare_except_guards(self):
        src = (
            "try:\n"
            '    StudentProfile.objects.only("bogus")\n'
            "except:\n"
            "    pass\n"
        )
        guarded = mod._guarded_linenos(ast.parse(src))
        self.assertIn(2, guarded)

    def test_named_tuple_alias_guard(self):
        src = (
            "_ERRS = (FieldError, ValueError)\n"
            "try:\n"
            '    StudentProfile.objects.defer("bogus")\n'
            "except _ERRS:\n"
            "    pass\n"
        )
        guarded = mod._guarded_linenos(ast.parse(src))
        self.assertIn(3, guarded)

    def test_unrelated_except_does_not_guard(self):
        src = (
            "try:\n"
            '    StudentProfile.objects.only("bogus")\n'
            "except KeyError:\n"
            "    pass\n"
        )
        self.assertNotIn(2, mod._guarded_linenos(ast.parse(src)))

    def test_marker_same_line_and_line_above(self):
        lines = [
            "x = 1",
            'M.objects.only("a")  # field-ref-allow: dynamic',
            "# field-ref-allow: next line is dynamic",
            'M.objects.values("b")',
        ]
        marked = mod._marked_linenos(lines)
        self.assertTrue(mod._is_excused(2, set(), marked))  # same line
        self.assertTrue(mod._is_excused(4, set(), marked))  # line above

    def test_unmarked_line_not_excused(self):
        lines = ['M.objects.only("a")']
        marked = mod._marked_linenos(lines)
        self.assertFalse(mod._is_excused(1, set(), marked))


class CollectTargetsTests(unittest.TestCase):
    def _collect_with_root(self, files: dict[str, str]) -> list[dict]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            apps = root / "apps"
            apps.mkdir()
            for rel, content in files.items():
                p = apps / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            old_root, old_apps = mod.REPO_ROOT, mod.APPS_DIR
            # Point REPO_ROOT at the temp root so the implicit `services/` scan
            # (REPO_ROOT / "services", which does not exist here) is a no-op.
            mod.REPO_ROOT, mod.APPS_DIR = root, apps
            try:
                return mod._collect_targets()
            finally:
                mod.REPO_ROOT, mod.APPS_DIR = old_root, old_apps

    def test_collects_resolvable_head(self):
        targets = self._collect_with_root(
            {"a/v.py": 'Evaluation.objects.only("seq1", "exam")\n'}
        )
        fields = sorted(t["field"] for t in targets)
        self.assertEqual(fields, ["exam", "seq1"])
        self.assertEqual({t["model"] for t in targets}, {"Evaluation"})
        self.assertEqual({t["method"] for t in targets}, {"only"})

    def test_collects_each_field_method(self):
        src = "\n".join(
            f'Evaluation.objects.{meth}("f")' for meth in sorted(mod._FIELD_METHODS)
        )
        targets = self._collect_with_root({"a/v.py": src + "\n"})
        self.assertEqual(
            {t["method"] for t in targets}, set(mod._FIELD_METHODS)
        )

    def test_skips_test_files(self):
        targets = self._collect_with_root(
            {"a/test_v.py": 'Evaluation.objects.only("bogus")\n'}
        )
        self.assertEqual(targets, [])

    def test_skips_migrations(self):
        targets = self._collect_with_root(
            {"a/migrations/0001_initial.py": 'Evaluation.objects.only("bogus")\n'}
        )
        self.assertEqual(targets, [])

    def test_marker_excuses_collection(self):
        targets = self._collect_with_root(
            {
                "a/v.py": (
                    'Evaluation.objects.only("bogus")  '
                    "# field-ref-allow: dynamic field set\n"
                )
            }
        )
        self.assertEqual(targets, [])

    def test_guard_excuses_collection(self):
        targets = self._collect_with_root(
            {
                "a/v.py": (
                    "try:\n"
                    '    Evaluation.objects.values("bogus")\n'
                    "except FieldError:\n"
                    "    pass\n"
                )
            }
        )
        self.assertEqual(targets, [])

    def test_unresolvable_head_not_collected(self):
        targets = self._collect_with_root(
            {"a/v.py": 'self.get_queryset().only("bogus")\n'}
        )
        self.assertEqual(targets, [])

    def test_annotate_chain_not_collected(self):
        targets = self._collect_with_root(
            {"a/v.py": 'Evaluation.objects.annotate(n=Count("x")).values("n")\n'}
        )
        self.assertEqual(targets, [])

    def test_pk_literal_not_collected(self):
        targets = self._collect_with_root(
            {"a/v.py": 'Evaluation.objects.only("pk")\n'}
        )
        self.assertEqual(targets, [])


if __name__ == "__main__":
    unittest.main()
