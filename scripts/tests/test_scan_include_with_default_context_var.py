"""Stdlib tests for scan_include_with_default_context_var (eager filter-arg 500s)."""

from __future__ import annotations

import importlib.util
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
    def test_flags_ops_surface_in_include(self):
        mod = _load()
        text = (
            '{% include "x.html" with page_host=page_host|default:ops_surface'
            '|default:"operator" %}'
        )
        findings = mod._scan_text(Path("t.html"), text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0][1], "ops_surface")

    def test_flags_plain_variable_default_anywhere(self):
        """Django 5.2 raises even outside {% include %} when the default arg is missing."""
        mod = _load()
        text = "{{ PREVIEW_BANNER_TEXT|default:PREVIEW_NOTE|default:\"x\" }}"
        findings = mod._scan_text(Path("t.html"), text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0][1], "PREVIEW_NOTE")

    def test_flags_with_tag_default(self):
        mod = _load()
        text = "{% with theme=SITE_ADMIN_THEME|default:SITE_THEME %}{{ theme }}{% endwith %}"
        findings = mod._scan_text(Path("t.html"), text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0][1], "SITE_THEME")

    def test_flags_slice_and_add_context_vars(self):
        mod = _load()
        text = (
            "{% for x in items|slice:backend_max_items_slice %}{{ x }}{% endfor %}\n"
            "{{ a|add:missing_b }}"
        )
        findings = mod._scan_text(Path("t.html"), text)
        vars_found = {f[1] for f in findings}
        self.assertEqual(vars_found, {"backend_max_items_slice", "missing_b"})

    def test_allows_literal_and_gettext_defaults(self):
        mod = _load()
        text = (
            '{% include "x.html" with a=b|default:"" c=d|default:_("Hi") '
            "e=f|default:None g=h|default:False %}\n"
            '{% for x in items|slice:":5" %}{{ x }}{% endfor %}\n'
            "{{ a|add:2 }}"
        )
        self.assertEqual(mod._scan_text(Path("t.html"), text), [])

    def test_skips_dotted_same_object_defaults(self):
        mod = _load()
        text = (
            '{% include "x.html" with report_subtitle=invoice.reference'
            "|default:invoice.id %}"
        )
        self.assertEqual(mod._scan_text(Path("t.html"), text), [])

    def test_honors_default_fallback_allow_marker(self):
        mod = _load()
        text = (
            "{% for s in students %}\n"
            "{{ s.get_full_name|default:s }}{# default-fallback-allow: s is for-loop student #}\n"
            "{% endfor %}\n"
            "{{ open_n|add:ack_n }}{# default-fallback-allow: ack_n bound by enclosing with #}\n"
        )
        self.assertEqual(mod._scan_text(Path("t.html"), text), [])

    def test_clean_tree_has_zero_findings(self):
        mod = _load()
        self.assertEqual(mod.scan(), [])


if __name__ == "__main__":
    unittest.main()
