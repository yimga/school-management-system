"""Stdlib tests for scan_include_with_default_context_var."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "scan_include_with_default_context_var.py"


def _load():
    spec = importlib.util.spec_from_file_location("scan_include_with_default", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class ScanIncludeWithDefaultContextVarTests(unittest.TestCase):
    def test_flags_ops_surface_default(self):
        mod = _load()
        text = (
            '{% include "x.html" with page_host=page_host|default:ops_surface'
            '|default:"operator" %}'
        )
        findings = mod._scan_text(Path("t.html"), text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0][1], "ops_surface")

    def test_allows_literal_and_gettext_defaults(self):
        mod = _load()
        text = (
            '{% include "x.html" with a=b|default:"" c=d|default:_("Hi") '
            "e=f|default:None g=h|default:False %}"
        )
        self.assertEqual(mod._scan_text(Path("t.html"), text), [])

    def test_skips_dotted_same_object_defaults(self):
        mod = _load()
        text = (
            '{% include "x.html" with report_subtitle=invoice.reference'
            "|default:invoice.id %}"
        )
        self.assertEqual(mod._scan_text(Path("t.html"), text), [])

    def test_clean_tree_has_zero_findings(self):
        mod = _load()
        self.assertEqual(mod.scan(), [])


if __name__ == "__main__":
    unittest.main()
