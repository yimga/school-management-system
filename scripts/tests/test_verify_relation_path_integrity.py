"""Stdlib unit tests for the AST/guard/marker layer of
``verify_relation_path_integrity`` (no Django required).

The runtime ``_meta.get_field`` resolution is exercised live in
``ci.yml::django-tests``; here we lock the static collection that decides WHICH
calls become targets and which are excused.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "verify_relation_path_integrity.py"
_spec = importlib.util.spec_from_file_location("verify_relation_path_integrity", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["verify_relation_path_integrity"] = mod
_spec.loader.exec_module(mod)


def _call(src: str) -> ast.Call:
    """First Call node whose attr is a relation method in a snippet."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in mod._RELATION_METHODS
        ):
            return node
    raise AssertionError("no relation-method call found")


class ResolveModelHeadTests(unittest.TestCase):
    def test_direct_objects_head(self):
        c = _call('Evaluation.objects.select_related("subject_assignment")')
        self.assertEqual(mod._resolve_model_head(c.func.value), "Evaluation")

    def test_head_through_filter(self):
        c = _call('Evaluation.objects.filter(x=1).select_related("a")')
        self.assertEqual(mod._resolve_model_head(c.func.value), "Evaluation")

    def test_lowercase_head_skipped(self):
        # `qs` is not a Capitalised model class name.
        c = _call('qs.objects.select_related("a")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_non_objects_head_skipped(self):
        c = _call('self.get_queryset().select_related("a")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_annotate_in_chain_skipped(self):
        c = _call('Evaluation.objects.annotate(n=Count("x")).select_related("a")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_union_in_chain_skipped(self):
        c = _call('Evaluation.objects.union(other).prefetch_related("a")')
        self.assertIsNone(mod._resolve_model_head(c.func.value))


class RelationLiteralsTests(unittest.TestCase):
    def test_multiple_positional(self):
        c = _call('M.objects.select_related("a", "b")')
        self.assertEqual(mod._relation_literals(c), ["a", "b"])

    def test_first_segment_only(self):
        c = _call('M.objects.select_related("a__b__c")')
        self.assertEqual(mod._relation_literals(c), ["a"])

    def test_pk_skipped(self):
        c = _call('M.objects.prefetch_related("pk")')
        self.assertEqual(mod._relation_literals(c), [])

    def test_non_constant_args_ignored(self):
        # Prefetch(...) object / variable args are not string Constants.
        c = _call('M.objects.prefetch_related(Prefetch("a"), some_var)')
        self.assertEqual(mod._relation_literals(c), [])

    def test_empty_string_skipped(self):
        c = _call('M.objects.select_related("")')
        self.assertEqual(mod._relation_literals(c), [])


class GuardAndMarkerTests(unittest.TestCase):
    def test_try_except_fielderror_guards(self):
        src = (
            "try:\n"
            '    Evaluation.objects.select_related("bogus")\n'
            "except FieldError:\n"
            "    pass\n"
        )
        tree = ast.parse(src)
        guarded = mod._guarded_linenos(tree)
        self.assertIn(2, guarded)

    def test_named_tuple_alias_guard(self):
        src = (
            "_ERRS = (FieldError, ValueError)\n"
            "try:\n"
            '    Evaluation.objects.prefetch_related("bogus")\n'
            "except _ERRS:\n"
            "    pass\n"
        )
        tree = ast.parse(src)
        guarded = mod._guarded_linenos(tree)
        self.assertIn(3, guarded)

    def test_unrelated_except_does_not_guard(self):
        src = (
            "try:\n"
            '    Evaluation.objects.select_related("bogus")\n'
            "except KeyError:\n"
            "    pass\n"
        )
        tree = ast.parse(src)
        self.assertNotIn(2, mod._guarded_linenos(tree))

    def test_marker_same_line_and_line_above(self):
        lines = [
            "x = 1",
            'M.objects.select_related("a")  # relation-path-allow: dynamic',
            "# relation-path-allow: next line is dynamic",
            'M.objects.select_related("b")',
        ]
        marked = mod._marked_linenos(lines)
        self.assertTrue(mod._is_excused(2, set(), marked))  # same line
        self.assertTrue(mod._is_excused(4, set(), marked))  # line above


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
            mod.REPO_ROOT, mod.APPS_DIR = root, apps
            try:
                return mod._collect_targets()
            finally:
                mod.REPO_ROOT, mod.APPS_DIR = old_root, old_apps

    def test_collects_resolvable_head(self):
        targets = self._collect_with_root(
            {"a/v.py": 'Evaluation.objects.select_related("component", "subject")\n'}
        )
        fields = sorted(t["field"] for t in targets)
        self.assertEqual(fields, ["component", "subject"])
        self.assertEqual({t["model"] for t in targets}, {"Evaluation"})

    def test_skips_test_files(self):
        targets = self._collect_with_root(
            {"a/test_v.py": 'Evaluation.objects.select_related("bogus")\n'}
        )
        self.assertEqual(targets, [])

    def test_marker_excuses_collection(self):
        targets = self._collect_with_root(
            {
                "a/v.py": (
                    'Evaluation.objects.select_related("bogus")  '
                    "# relation-path-allow: dynamic graph\n"
                )
            }
        )
        self.assertEqual(targets, [])

    def test_unresolvable_head_not_collected(self):
        targets = self._collect_with_root(
            {"a/v.py": 'self.get_queryset().select_related("bogus")\n'}
        )
        self.assertEqual(targets, [])


if __name__ == "__main__":
    unittest.main()
