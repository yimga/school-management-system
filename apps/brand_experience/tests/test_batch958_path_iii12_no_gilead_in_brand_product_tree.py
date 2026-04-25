"""SOT §11.4 batch 958 — PATH §6.6 III.12: no Gilead literals in brand_experience product code."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

_BRAND_ROOT = Path(__file__).resolve().parents[1]
_SKIP_DIR_PARTS = frozenset({"migrations", "tests"})


class Batch958PathIii12NoGileadInBrandProductTreeTests(SimpleTestCase):
    def test_brand_experience_product_py_excludes_gilead_literal(self):
        for path in _BRAND_ROOT.rglob("*.py"):
            rel = path.relative_to(_BRAND_ROOT)
            if _SKIP_DIR_PARTS & set(rel.parts):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "gilead",
                text.lower(),
                msg=f"Unexpected rebrand residue in {path.as_posix()}",
            )
