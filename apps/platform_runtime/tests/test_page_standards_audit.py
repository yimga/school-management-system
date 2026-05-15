"""Tests for the section_page_scaffold partial + audit_page_standards verifier."""

from __future__ import annotations

from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[3]


class SectionPageScaffoldRenderTests(SimpleTestCase):
    def test_scaffold_renders_skip_link(self):
        html = render_to_string(
            "components/section_page_scaffold.html",
            {
                "page_title": "Test page",
                "page_archetype": "dashboard",
            },
        )
        self.assertIn('href="#main-content"', html)

    def test_scaffold_renders_h1(self):
        html = render_to_string(
            "components/section_page_scaffold.html",
            {"page_title": "Test page"},
        )
        self.assertIn("<h1", html)
        self.assertIn("Test page", html)

    def test_scaffold_renders_breadcrumbs(self):
        html = render_to_string(
            "components/section_page_scaffold.html",
            {
                "page_title": "Detail",
                "breadcrumbs": [
                    {"label": "Home", "href": "/"},
                    {"label": "Section", "href": "/section/"},
                    {"label": "Detail"},
                ],
            },
        )
        self.assertIn('aria-label="Breadcrumb"', html)
        self.assertIn('aria-current="page"', html)
        self.assertIn("Home", html)
        self.assertIn("Detail", html)

    def test_scaffold_caps_primary_actions_at_three(self):
        actions = [
            {"label": f"Action {i}", "href": f"/a/{i}/"} for i in range(5)
        ]
        html = render_to_string(
            "components/section_page_scaffold.html",
            {"page_title": "T", "primary_actions": actions},
        )
        # Only the first 3 should render
        self.assertIn("Action 0", html)
        self.assertIn("Action 1", html)
        self.assertIn("Action 2", html)
        self.assertNotIn("Action 3", html)
        self.assertNotIn("Action 4", html)

    def test_scaffold_emits_data_page_archetype(self):
        html = render_to_string(
            "components/section_page_scaffold.html",
            {"page_title": "T", "page_archetype": "report"},
        )
        self.assertIn('data-page-archetype="report"', html)

    def test_scaffold_hide_skip_link_omits_anchor(self):
        html = render_to_string(
            "components/section_page_scaffold.html",
            {"page_title": "T", "hide_skip_link": True},
        )
        self.assertNotIn('href="#main-content"', html)


class AuditPageStandardsScriptTests(SimpleTestCase):
    """Smoke-test the verifier script: imports cleanly and counts > 0."""

    def test_audit_script_imports_and_finds_templates(self):
        # Run the script in-process to keep test fast.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_audit_page_standards",
            REPO_ROOT / "scripts" / "audit_page_standards.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        templates = module._iter_templates()
        self.assertGreater(len(templates), 100)  # the repo has many templates

    def test_audit_marks_partials(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_audit_page_standards",
            REPO_ROOT / "scripts" / "audit_page_standards.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        scaffold = REPO_ROOT / "templates" / "components" / "section_page_scaffold.html"
        self.assertTrue(scaffold.exists())
        result = module._audit_one(scaffold)
        # Partials skip page-level checks
        self.assertTrue(result["is_partial"])
        # And the scaffold itself does not extend a base
        self.assertFalse(result["extends_base"])
        # So it should NOT carry missing_main_landmark / missing_h1 findings
        for f in result["findings"]:
            self.assertNotIn("missing_main_landmark", f)

    def test_audit_detects_missing_csrf(self):
        import importlib.util
        import tempfile
        spec = importlib.util.spec_from_file_location(
            "_audit_page_standards",
            REPO_ROOT / "scripts" / "audit_page_standards.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Build a test fixture with a form but no csrf_token.
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".html", delete=False
        ) as f:
            f.write('<form method="post"><input name="x"></form>')
            tmp_path = Path(f.name)
        try:
            result = module._audit_one(tmp_path)
            self.assertIn("form_missing_csrf_token", result["findings"])
        finally:
            tmp_path.unlink(missing_ok=True)
