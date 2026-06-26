"""Stdlib unittest coverage for ``verify_static_reference_integrity`` (scan layer).

The runtime resolution phase needs Django's staticfiles finders (exercised in
CI's django-tests job + by the verifier's own --compare). These tests lock the
pure, no-Django collection layer: which ``{% static %}`` tag shapes are
recognized as literal references, which are correctly left to runtime
(variables, filtered concatenations), the ``as var`` capture form, the
directory-prefix literal, the ``static-ref-allow`` marker, and the
templates-dir / extension file walk.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_static_reference_integrity as v  # noqa: E402


def _paths(line: str) -> list[str]:
    return [m.group("path") for m in v._STATIC_TAG.finditer(line)]


class StaticTagRegexTests(unittest.TestCase):
    def test_single_and_double_quote_literals(self):
        self.assertEqual(_paths("{% static 'css/app.css' %}"), ["css/app.css"])
        self.assertEqual(_paths('{% static "js/app.js" %}'), ["js/app.js"])

    def test_as_var_capture_form(self):
        self.assertEqual(
            _paths('<link href="{% static "css/app.css" as href %}">'), ["css/app.css"]
        )

    def test_extra_whitespace(self):
        self.assertEqual(_paths("{%  static   'x/y.css'   %}"), ["x/y.css"])

    def test_directory_prefix_literal_is_captured(self):
        # resolution (finders) is the runtime layer's job; the SCAN must still
        # capture the literal so it can be checked.
        self.assertEqual(
            _paths("{% static 'js/vendor/tesseract/' %}"), ["js/vendor/tesseract/"]
        )

    def test_two_refs_on_one_line(self):
        self.assertEqual(
            _paths("{% static 'a.css' %} and {% static 'b.js' %}"), ["a.css", "b.js"]
        )

    def test_variable_arg_not_matched(self):
        self.assertEqual(_paths("{% static asset_path %}"), [])
        self.assertEqual(_paths("{% static logo_url %}"), [])

    def test_filtered_concatenation_not_matched(self):
        # `{% static "a"|add:rest %}` is dynamic — must be left to runtime.
        self.assertEqual(_paths('{% static "base/"|add:name %}'), [])

    def test_non_static_tag_not_matched(self):
        self.assertEqual(_paths("{% url 'home' %}"), [])
        self.assertEqual(_paths("{% include 'x.html' %}"), [])


class MarkerTests(unittest.TestCase):
    def test_marked_linenos_finds_allow_marker(self):
        lines = [
            "<img src=\"{% static 'img/wip.png' %}\">  {# static-ref-allow: ships next sprint #}",
            "{# static-ref-allow: above #}",
            "<img src=\"{% static 'img/later.png' %}\">",
            "<img src=\"{% static 'img/real.png' %}\">",
        ]
        marked = v._marked_linenos(lines)
        self.assertEqual(marked, {1, 2})

    def test_is_excused_same_line_and_line_above(self):
        marked = {2}
        self.assertTrue(v._is_excused(2, marked))   # same line
        self.assertTrue(v._is_excused(3, marked))   # line below a marker line
        self.assertFalse(v._is_excused(5, marked))  # unrelated line


class CollectionWalkTests(unittest.TestCase):
    """End-to-end of the no-Django collection layer against a temp repo tree."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self._orig_root = v.REPO_ROOT
        v.REPO_ROOT = self.root

    def tearDown(self):
        v.REPO_ROOT = self._orig_root
        self._tmp.cleanup()

    def _write(self, rel: str, body: str):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def _assets(self):
        return sorted(t["asset"] for t in v._collect_targets())

    def test_collects_from_templates_dir_html(self):
        self._write("templates/page.html", "<link href=\"{% static 'css/a.css' %}\">")
        self.assertEqual(self._assets(), ["css/a.css"])

    def test_collects_from_app_templates_dir(self):
        self._write(
            "apps/portal/templates/portal/home.html",
            "<script src=\"{% static 'js/h.js' %}\"></script>",
        )
        self.assertEqual(self._assets(), ["js/h.js"])

    def test_marker_excuses_ref(self):
        self._write(
            "templates/wip.html",
            "<img src=\"{% static 'img/wip.png' %}\">  {# static-ref-allow: soon #}\n",
        )
        self.assertEqual(self._assets(), [])

    def test_non_literal_ref_not_collected(self):
        self._write("templates/dyn.html", "<img src=\"{% static logo %}\">")
        self.assertEqual(self._assets(), [])

    def test_non_template_extension_skipped(self):
        # a .py file under templates/ is not a text template we resolve
        self._write("templates/notes.py", "x = \"{% static 'css/a.css' %}\"")
        self.assertEqual(self._assets(), [])

    def test_html_outside_templates_dir_ignored(self):
        # mockups / fixtures not under a templates/ dir are not Django-loaded
        self._write("static/mockup.html", "<link href=\"{% static 'css/x.css' %}\">")
        self.assertEqual(self._assets(), [])

    def test_skip_dirs_excluded(self):
        self._write(
            "node_modules/pkg/templates/t.html", "<link href=\"{% static 'css/z.css' %}\">"
        )
        self.assertEqual(self._assets(), [])

    def test_svg_and_txt_templates_scanned(self):
        self._write("templates/logo.svg", "<image href=\"{% static 'img/logo.svg' %}\"/>")
        self._write("templates/email/welcome.txt", "{% static 'img/banner.png' %}")
        self.assertEqual(self._assets(), ["img/banner.png", "img/logo.svg"])


if __name__ == "__main__":
    unittest.main()
