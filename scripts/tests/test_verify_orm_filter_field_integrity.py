"""Stdlib unit tests for the AST/guard/marker layer of
``verify_orm_filter_field_integrity`` (no Django required).

The runtime ``_meta.get_field`` resolution is exercised live in
``ci.yml::django-tests``; here we lock the static collection that decides WHICH
lookup keys become targets and which are excused.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "verify_orm_filter_field_integrity.py"
_spec = importlib.util.spec_from_file_location(
    "verify_orm_filter_field_integrity", _SCRIPT
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["verify_orm_filter_field_integrity"] = mod
_spec.loader.exec_module(mod)


def _call(src: str) -> ast.Call:
    """First Call node whose attr is a lookup method in a snippet."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in mod._LOOKUP_METHODS
        ):
            return node
    raise AssertionError("no lookup-method call found")


class ResolveModelHeadTests(unittest.TestCase):
    def test_direct_objects_head(self):
        c = _call("ComplianceProfile.objects.filter(school=s)")
        self.assertEqual(mod._resolve_model_head(c.func.value), "ComplianceProfile")

    def test_head_through_filter_then_exclude(self):
        c = _call("Foo.objects.filter(a=1).exclude(b=2)")
        self.assertEqual(mod._resolve_model_head(c.func.value), "Foo")

    def test_lowercase_head_skipped(self):
        c = _call("qs.objects.filter(a=1)")
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_non_objects_head_skipped(self):
        c = _call("self.get_queryset().filter(a=1)")
        self.assertIsNone(mod._resolve_model_head(c.func.value))

    def test_annotate_in_chain_skipped(self):
        # A later .filter() may legitimately reference the annotation.
        c = _call('Foo.objects.annotate(n=Count("x")).filter(n__gt=1)')
        self.assertIsNone(mod._resolve_model_head(c.func.value))


class LookupKeyTests(unittest.TestCase):
    def test_single_kwarg(self):
        c = _call("Foo.objects.filter(school=s)")
        self.assertEqual(mod._lookup_keys(c, "filter"), ["school"])

    def test_lookup_suffix_reduced_to_first_segment(self):
        c = _call('Foo.objects.filter(name__icontains="x")')
        self.assertEqual(mod._lookup_keys(c, "filter"), ["name"])

    def test_relation_traversal_first_segment_only(self):
        c = _call('Foo.objects.filter(school__name="x")')
        self.assertEqual(mod._lookup_keys(c, "filter"), ["school"])

    def test_pk_and_id_skipped(self):
        self.assertEqual(mod._lookup_keys(_call("Foo.objects.get(pk=1)"), "get"), [])
        self.assertEqual(
            mod._lookup_keys(_call("Foo.objects.filter(id=1)"), "filter"), []
        )

    def test_kwargs_splat_skipped(self):
        c = _call("Foo.objects.filter(**criteria)")
        self.assertEqual(mod._lookup_keys(c, "filter"), [])

    def test_positional_q_object_not_seen(self):
        c = _call("Foo.objects.filter(Q(a=1) | Q(b=2))")
        self.assertEqual(mod._lookup_keys(c, "filter"), [])

    def test_defaults_skipped_for_create_family(self):
        c = _call('Foo.objects.get_or_create(staff_id=x, defaults={"a": 1})')
        self.assertEqual(mod._lookup_keys(c, "get_or_create"), ["staff_id"])
        c2 = _call('Foo.objects.update_or_create(code=x, defaults={"a": 1})')
        self.assertEqual(mod._lookup_keys(c2, "update_or_create"), ["code"])

    def test_defaults_not_skipped_for_filter(self):
        # `defaults` is special only on the create-family; on .filter it is a
        # normal lookup key and must still be checked.
        c = _call("Foo.objects.filter(defaults=1)")
        self.assertEqual(mod._lookup_keys(c, "filter"), ["defaults"])

    def test_multiple_kwargs_preserved(self):
        c = _call('Foo.objects.filter(school_id=s, key="x", is_active=True)')
        self.assertEqual(
            mod._lookup_keys(c, "filter"), ["school_id", "key", "is_active"]
        )


class GuardAndMarkerTests(unittest.TestCase):
    def test_try_except_fielderror_guards(self):
        src = "try:\n    Foo.objects.filter(bad=1)\nexcept FieldError:\n    pass\n"
        self.assertIn(2, mod._guarded_linenos(ast.parse(src)))

    def test_try_except_valueerror_does_not_guard(self):
        # ValueError is NOT a FieldError guard — the call stays a target.
        src = "try:\n    Foo.objects.filter(bad=1)\nexcept ValueError:\n    pass\n"
        self.assertNotIn(2, mod._guarded_linenos(ast.parse(src)))

    def test_allow_marker_line(self):
        lines = ["Foo.objects.filter(bad=1)  # filter-field-allow: reviewed"]
        self.assertEqual(mod._marked_linenos(lines), {1})


if __name__ == "__main__":
    unittest.main()
