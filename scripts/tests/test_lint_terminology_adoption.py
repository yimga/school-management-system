"""Stdlib unittest coverage for ``lint_terminology_adoption``.

Exercises helper predicates and ``_scan_template`` against synthetic HTML
under ``var/`` so the real template tree is never mutated.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lint_terminology_adoption as lint  # noqa: E402


class HelperPredicateTests(unittest.TestCase):
    def test_is_excluded_marketing_and_admin(self):
        self.assertTrue(lint._is_excluded("templates/marketing/home.html"))
        self.assertTrue(lint._is_excluded("templates/admin/base.html"))
        self.assertFalse(lint._is_excluded("templates/portal/dashboard.html"))

    def test_is_allowlisted_same_line_and_line_above(self):
        lines = [
            "<p>Student</p>",
            "<!-- terminology-adopt-allow: above -->",
            "<p>Student</p>",
            "<p>Student</p>  <!-- terminology-adopt-allow: fixture -->",
        ]
        self.assertFalse(lint._is_allowlisted(lines, 1))
        self.assertTrue(lint._is_allowlisted(lines, 3))
        self.assertTrue(lint._is_allowlisted(lines, 4))

    def test_line_uses_adoption_surface(self):
        self.assertTrue(lint._line_uses_adoption_surface("{% term 'student' %}"))
        self.assertTrue(lint._line_uses_adoption_surface("{% trans 'Student' %}"))
        self.assertFalse(lint._line_uses_adoption_surface("<p>Student roster</p>"))


class ScanTemplateSyntheticTests(unittest.TestCase):
    def _write_fixture(self, rel_dir: str, name: str, body: str) -> pathlib.Path:
        base = lint.REPO_ROOT / rel_dir
        base.mkdir(parents=True, exist_ok=True)
        path = base / name
        path.write_text(body, encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_flags_hardcoded_lexicon_literal(self):
        path = self._write_fixture(
            "var/test_terminology_lint",
            "portal_hardcoded.html",
            "<section>\n  <h2>Student roster</h2>\n</section>\n",
        )
        lexicon = lint._load_lexicon_terms()
        findings = lint._scan_template(path, lexicon)
        self.assertTrue(findings)
        self.assertEqual(findings[0]["path"], path.relative_to(lint.REPO_ROOT).as_posix())

    def test_skips_adoption_surface_and_allow_marker(self):
        path = self._write_fixture(
            "var/test_terminology_lint",
            "portal_adopted.html",
            "{% term 'student' as student_label %}\n"
            "<p>{{ student_label }} roster</p>\n"
            "<!-- terminology-adopt-allow: demo -->\n"
            "<p>Teacher notes</p>\n",
        )
        lexicon = lint._load_lexicon_terms()
        findings = lint._scan_template(path, lexicon)
        self.assertEqual(findings, [])

    def test_excluded_prefix_returns_no_findings(self):
        path = self._write_fixture(
            "templates/marketing/_lint_fixture",
            "excluded.html",
            "<p>Student gallery</p>\n",
        )
        lexicon = lint._load_lexicon_terms()
        findings = lint._scan_template(path, lexicon)
        self.assertEqual(findings, [])
        # Clean up empty marketing fixture dir if created
        try:
            path.parent.rmdir()
        except OSError:
            pass


class CompareMultisetTests(unittest.TestCase):
    def test_compare_detects_new_literal(self):
        baseline_findings = [
            {"path": "templates/x.html", "key": "student", "literal": "Student", "line": 1},
        ]
        current_findings = list(baseline_findings) + [
            {"path": "templates/y.html", "key": "teacher", "literal": "Teacher", "line": 2},
        ]
        with tempfile.TemporaryDirectory() as td:
            baseline_path = pathlib.Path(td) / "baseline.json"
            baseline_path.write_text(
                lint.json.dumps(
                    {
                        "finding_count": 1,
                        "findings": baseline_findings,
                    }
                ),
                encoding="utf-8",
            )
            original = lint.BASELINE_PATH
            lint.BASELINE_PATH = baseline_path
            self.addCleanup(lambda: setattr(lint, "BASELINE_PATH", original))
            exit_code = lint._compare(current_findings)
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
