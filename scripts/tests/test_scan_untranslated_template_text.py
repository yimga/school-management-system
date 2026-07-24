"""Unit tests for scripts/scan_untranslated_template_text.py (M21/G4)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan_untranslated_template_text as S  # noqa: E402


def _scan(html: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.html"
        p.write_text(html, encoding="utf-8")
        return S.scan_file(p)


def _texts(html: str) -> set[str]:
    return {f["text"] for f in _scan(html)}


class FlaggingTests(unittest.TestCase):
    def test_flags_hardcoded_button_label_heading(self):
        html = "<h1>Syllabus builder</h1><button>Save draft</button><label>Target class</label>"
        self.assertEqual(_texts(html), {"Syllabus builder", "Save draft", "Target class"})

    def test_flags_hardcoded_anchor_and_th_and_option(self):
        html = '<a href="/x">Back to syllabi</a><th>Subject</th><option>Registration lock</option>'
        self.assertEqual(_texts(html), {"Back to syllabi", "Subject", "Registration lock"})


class NonFlaggingTests(unittest.TestCase):
    def test_translated_label_not_flagged(self):
        self.assertEqual(_texts('<button>{% trans "Save draft" %}</button>'), set())

    def test_blocktrans_label_not_flagged(self):
        html = "<label>{% blocktrans %}Tag with standards{% endblocktrans %}</label>"
        self.assertEqual(_texts(html), set())

    def test_pure_variable_label_not_flagged(self):
        self.assertEqual(_texts("<a>{{ item.title }}</a>"), set())

    def test_acronym_only_not_flagged(self):
        # No natural-language word (>=3 letters + vowel).
        self.assertEqual(_texts("<button>PDF</button><th>ID</th>"), set())

    def test_script_and_comment_not_flagged(self):
        html = "<script><button>Save draft</button></script><!-- <a>Cancel</a> -->"
        self.assertEqual(_texts(html), set())

    def test_attribute_with_gt_does_not_break_matching(self):
        # `{% if a > b %}` inside an attribute must not corrupt element boundaries.
        html = '<a href="x" data-x="{% if a > b %}y{% endif %}">Cancel</a>'
        self.assertEqual(_texts(html), {"Cancel"})

    def test_non_label_paragraph_not_flagged(self):
        self.assertEqual(_texts("<p>This prose is out of scope for v1.</p>"), set())


class AllowMarkerTests(unittest.TestCase):
    def test_line_marker_suppresses(self):
        html = '<button>Save draft</button> {# i18n-allow: demo #}'
        self.assertEqual(_texts(html), set())

    def test_file_marker_suppresses_all(self):
        html = "{# i18n-allow-file: email body #}\n<button>Save draft</button><h1>Report</h1>"
        self.assertEqual(_texts(html), set())


class CompareShapeTests(unittest.TestCase):
    def test_payload_and_keying(self):
        findings = _scan("<button>Save draft</button>")
        payload = S._payload(findings)
        self.assertEqual(payload["finding_count"], 1)
        self.assertEqual(S._key(findings[0]), (findings[0]["path"], "button", "Save draft"))


if __name__ == "__main__":
    unittest.main()
