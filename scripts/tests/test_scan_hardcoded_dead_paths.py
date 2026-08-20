"""Lock the detector so the gate cannot be quietly neutered.

A zero-baseline gate is only worth what its detector is worth: once the tree is
clean, a scanner that has stopped detecting anything reports exactly the same
"0 finding(s)" as one that works. These tests pin the shapes it must catch and,
just as importantly, the shapes it must stay silent about — a gate that cries
wolf gets switched off, which is the failure mode that matters most here.

Stdlib only, no Django: these cover the candidate-extraction layer. Resolution
itself is delegated to Django's own resolver in ``_findings()``, which is ground
truth and needs no test of ours.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import scan_hardcoded_dead_paths as gate  # noqa: E402


def _paths(source: str, tmp: Path, name: str = "views.py"):
    """Run the extractor over one synthetic module inside a temp apps/ tree."""
    app = tmp / "apps" / "demo"
    app.mkdir(parents=True, exist_ok=True)
    (app / name).write_text(source, encoding="utf-8")
    original = gate.REPO_ROOT
    gate.REPO_ROOT = tmp
    try:
        return [target for _rel, _line, target in gate._candidates()]
    finally:
        gate.REPO_ROOT = original


class TheDetectorFiresTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(__file__).parent / "_tmp_dead_paths"

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_a_dict_href_is_a_candidate(self):
        found = _paths('PANELS = [{"href": "/operator/thing/"}]\n', self._tmp)
        self.assertIn("/operator/thing/", found)

    def test_a_keyword_url_is_a_candidate(self):
        found = _paths('Action(label="x", url="/finance/invoices/")\n', self._tmp)
        self.assertIn("/finance/invoices/", found)

    def test_every_navigation_key_is_covered(self):
        for key in ("url", "href", "link", "endpoint", "target_url", "cta_url"):
            with self.subTest(key=key):
                found = _paths(f'X = {{"{key}": "/a/b/"}}\n', self._tmp)
                self.assertIn("/a/b/", found)


class TheDetectorStaysSilentTests(unittest.TestCase):
    """Every one of these was a real false positive during development."""

    def setUp(self):
        self._tmp = Path(__file__).parent / "_tmp_dead_paths_quiet"

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_a_static_asset_is_not_navigation(self):
        found = _paths('X = {"href": "/static/css/app.css"}\n', self._tmp)
        self.assertEqual(found, [])

    def test_a_runtime_built_path_is_not_checkable(self):
        for path in ("/school/%s/", "/school/{slug}/", "/finance/..."):
            with self.subTest(path=path):
                found = _paths(f'X = {{"url": "{path}"}}\n', self._tmp)
                self.assertEqual(found, [])

    def test_a_relative_path_is_not_a_candidate(self):
        found = _paths('X = {"href": "reports/"}\n', self._tmp)
        self.assertEqual(found, [])

    def test_the_marker_excuses_the_same_line(self):
        found = _paths(
            'X = {"href": "/nowhere/"}  # dead-path-allow: external mount\n', self._tmp
        )
        self.assertEqual(found, [])

    def test_the_marker_excuses_the_line_above(self):
        source = "X = {\n    # dead-path-allow: external mount\n    \"href\": \"/nowhere/\",\n}\n"
        self.assertEqual(_paths(source, self._tmp), [])

    def test_tests_are_not_scanned(self):
        app = self._tmp / "apps" / "demo" / "tests"
        app.mkdir(parents=True, exist_ok=True)
        (app / "test_x.py").write_text('X = {"href": "/nowhere/"}\n', encoding="utf-8")
        original = gate.REPO_ROOT
        gate.REPO_ROOT = self._tmp
        try:
            self.assertEqual(list(gate._candidates()), [])
        finally:
            gate.REPO_ROOT = original


def _template_paths(source: str, tmp, name: str = "page.html"):
    """Run the template extractor over one synthetic template."""
    root = tmp / "templates"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(source, encoding="utf-8")
    original = gate.REPO_ROOT
    gate.REPO_ROOT = tmp
    try:
        return [target for _rel, _line, target in gate._template_candidates()]
    finally:
        gate.REPO_ROOT = original


class TemplateLiteralsAreCoveredTests(unittest.TestCase):
    """{% url %} gates never see a path written as a plain string."""

    def setUp(self):
        self._tmp = Path(__file__).parent / "_tmp_dead_paths_tpl"

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_an_href_is_a_candidate(self):
        found = _template_paths('<a href="/nowhere/">x</a>\n', self._tmp)
        self.assertIn("/nowhere/", found)

    def test_a_form_action_is_a_candidate(self):
        """The real bug: a POST target that existed on no host."""
        found = _template_paths('<form action="/nowhere/" method="post">\n', self._tmp)
        self.assertIn("/nowhere/", found)

    def test_a_django_variable_is_not_a_literal(self):
        found = _template_paths('<a href="/x/{{ obj.pk }}/">x</a>\n', self._tmp)
        self.assertEqual(found, [])

    def test_a_static_asset_is_skipped(self):
        found = _template_paths('<a href="/static/x.css">x</a>\n', self._tmp)
        self.assertEqual(found, [])

    def test_the_marker_excuses_the_line_above(self):
        source = ("<!-- dead-path-allow: external -->\n"
                  '<a href="/nowhere/">x</a>\n')
        self.assertEqual(_template_paths(source, self._tmp), [])

    def test_the_live_tree_still_yields_template_candidates(self):
        found = [t for _r, _l, t in gate._template_candidates()]
        self.assertGreater(
            len(found), 5, "the template arm stopped finding anything"
        )


class TheCatchAllHostStaysOutTests(unittest.TestCase):
    """config.docs_urls ends in <path:_unused> and matches ANY path.

    Adding it to HOST_URLCONFS would make every literal resolve, so the gate
    would report zero forever while detecting nothing. A green gate and a dead
    gate look identical from the outside; this test is the difference.
    """

    def test_docs_urls_is_not_a_host_we_resolve_against(self):
        self.assertNotIn("config.docs_urls", gate.HOST_URLCONFS)

    def test_api_urls_is_not_a_host_we_resolve_against(self):
        self.assertNotIn("config.api_urls", gate.HOST_URLCONFS)


class TheLiveTreeIsCleanTests(unittest.TestCase):
    """Calibration: proves 0 means clean, not that the scanner found nothing."""

    def test_the_repo_still_has_navigation_paths_to_check(self):
        found = [target for _rel, _line, target in gate._candidates()]
        self.assertGreater(
            len(found),
            20,
            "the extractor stopped finding candidates — a silently dead gate",
        )


if __name__ == "__main__":
    unittest.main()
