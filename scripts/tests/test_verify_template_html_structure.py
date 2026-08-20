"""Tests for the template HTML-structure gate.

Every case below is a real shape from this tree, not an invented one. The defect cases
are the nine found on 2026-08-20 reduced to their smallest reproducing form; the
non-defect cases are the idioms that a naive checker gets wrong and that would make this
gate noisy enough to be ignored.

Two of these exist because the gate itself was wrong first:
  * ``test_comment_mentioning_style_does_not_swallow_markup`` -- stripping ``<style>``
    before ``{% comment %}`` let a comment whose prose mentions "<style>" eat the
    ``{% endcomment %}`` and every tag up to the next ``</style>``. That produced a clean
    false positive on four email templates.
  * ``test_conditional_wrapper_idiom_is_not_a_finding`` -- ``{% if x %}<a>{% else %}<div>``
    paired with a matching close is correct, and flagging it fired on four live files.

The live-tree test at the bottom doubles as calibration: if this gate reports a finding
on a clean checkout, it is the gate that is wrong, not the tree.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verify_template_html_structure as gate  # noqa: E402


class _TempTree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._real_root = gate.REPO_ROOT
        gate.REPO_ROOT = self.root
        (self.root / "templates").mkdir(parents=True)

    def tearDown(self):
        gate.REPO_ROOT = self._real_root
        self._tmp.cleanup()

    def _write(self, name, text):
        path = self.root / "templates" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _findings(self, name, text):
        return gate.check(self._write(name, text))


class BalanceTests(_TempTree):
    def test_balanced_template_is_clean(self):
        self.assertEqual(self._findings("ok.html", "<div><div></div></div>\n"), [])

    def test_missing_closer_is_reported(self):
        found = self._findings("bad.html", '<div id="section-today">\n<section></section>\n')
        self.assertTrue(any("net <div> delta +1" in f for f in found), found)

    def test_surplus_closer_is_reported(self):
        found = self._findings("bad.html", "<div></div></div>\n")
        self.assertTrue(any("net <div> delta -1" in f for f in found), found)

    def test_unclosed_details_is_reported(self):
        """siteconfig/report_library.html: <details> per row, no </details> in the file."""
        found = self._findings(
            "rows.html",
            "<table><tbody>\n{% for r in rows %}\n"
            "<tr><td><details><summary>x</summary><div>y</div></td></tr>\n"
            "{% endfor %}\n</tbody></table>\n",
        )
        self.assertTrue(any("net <details> delta +1" in f for f in found), found)

    def test_loop_body_that_nests_is_reported(self):
        found = self._findings(
            "loop.html",
            "<div>\n{% for r in rows %}\n<div>{{ r }}\n{% endfor %}\n</div>\n",
        )
        self.assertTrue(
            any("body changes <div> depth by +1 per iteration" in f for f in found), found
        )

    def test_empty_branch_mismatch_is_reported(self):
        """compliance/data_rights_queue.html: a disclosure opened in {% empty %} only."""
        found = self._findings(
            "empty.html",
            "{% for r in rows %}\n<tr><td>{{ r }}</td></tr>\n"
            "{% empty %}\n<tr><td><details><summary>a</summary></td></tr>\n"
            "{% endfor %}\n",
        )
        self.assertTrue(any("{% empty %}" in f for f in found), found)


class UnknownTagTests(_TempTree):
    def test_motion_close_tag_is_reported(self):
        """marketplace/*.html shipped </motion>, an element that does not exist."""
        found = self._findings("m.html", "<div>\n</motion>\n")
        self.assertTrue(any("</motion> is not an HTML or SVG element" in f for f in found),
                        found)

    def test_custom_element_is_not_a_finding(self):
        self.assertEqual(self._findings("ce.html", "<my-widget></my-widget>\n"), [])

    def test_svg_camelcase_tags_are_known(self):
        found = self._findings(
            "svg.html",
            "<svg><defs><radialGradient><stop /></radialGradient>"
            "<filter><feMerge></feMerge><feComponentTransfer></feComponentTransfer>"
            "</filter></defs></svg>\n",
        )
        self.assertEqual(found, [])

    def test_unknown_tag_is_reported_even_under_the_allow_marker(self):
        """The waiver covers deliberate imbalance. A bogus element is never deliberate."""
        found = self._findings(
            "w.html",
            "{# html-structure-allow: paired with its sibling close partial #}\n"
            "<div>\n</motion>\n",
        )
        self.assertTrue(any("</motion>" in f for f in found), found)
        self.assertFalse(any("net <div>" in f for f in found), found)


class NoiseTests(_TempTree):
    def test_conditional_wrapper_idiom_is_not_a_finding(self):
        """components/dashboard/rmc_dh_tile.html renders <a> or <div>, and closes to match."""
        found = self._findings(
            "tile.html",
            '{% if href %}<a class="t" href="{{ href }}">{% else %}<div class="t">{% endif %}\n'
            "<div>body</div>\n"
            "{% if href %}</a>{% else %}</div>{% endif %}\n",
        )
        self.assertEqual(found, [])

    def test_mutually_exclusive_branches_with_equal_delta_are_clean(self):
        """evals/compliance_dashboard.html: three progress-bar branches, one renders."""
        found = self._findings(
            "bar.html",
            '<div class="progress">\n'
            "{% if p >= 75 %}\n<div class=\"bar ok\">\n"
            "{% elif p >= 50 %}\n<div class=\"bar warn\">\n"
            "{% else %}\n<div class=\"bar bad\">\n{% endif %}\n"
            "{{ p }}%\n</div>\n</div>\n",
        )
        self.assertEqual(found, [])

    def test_divs_inside_script_and_style_are_ignored(self):
        found = self._findings(
            "js.html",
            "<div>\n<script>const t = '<div><div>';</script>\n"
            "<style>.x{}</style>\n</div>\n",
        )
        self.assertEqual(found, [])

    def test_comment_mentioning_style_does_not_swallow_markup(self):
        """Django comments must be stripped BEFORE <style>, or real markup disappears."""
        found = self._findings(
            "email.html",
            "{% comment %}\n  inline attributes plus a <style> block for clients.\n"
            "{% endcomment %}\n<style>.a{color:red}</style>\n"
            "<table><tbody><tr><td>x</td></tr></tbody></table>\n",
        )
        self.assertEqual(found, [])

    def test_self_closing_div_is_not_counted_as_an_open(self):
        self.assertEqual(self._findings("sc.html", "<div/>\n"), [])

    def test_optional_end_tags_are_not_flagged(self):
        """<li>/<td>/<tr>/<p> may legally omit their close; flagging them would be noise."""
        found = self._findings(
            "opt.html",
            "<ul><li>one<li>two</ul>\n<table><tbody><tr><td>a<td>b</tbody></table>\n",
        )
        self.assertEqual(found, [])


class WaiverTests(_TempTree):
    def test_allow_marker_waives_a_deliberate_pair(self):
        found = self._findings(
            "open.html",
            "{# html-structure-allow: opens the row, closed by the _close sibling #}\n"
            '<div class="row">\n',
        )
        self.assertEqual(found, [])

    def test_marker_without_a_reason_does_not_waive(self):
        found = self._findings(
            "open.html", "{# html-structure-allow: x #}\n<div>\n"
        )
        self.assertTrue(any("net <div> delta +1" in f for f in found), found)


class LineNumberTests(_TempTree):
    def test_line_numbers_survive_a_stripped_script_block(self):
        """Blanking must preserve newlines, or every reported line after one is wrong."""
        text = (
            "<div>\n"              # 1
            "<script>\n\n\n\n"     # 2, 3, 4, 5
            "</script>\n"          # 6
            "{% for r in rows %}\n"  # 7  <- the finding belongs here
            "<div>\n"              # 8
            "{% endfor %}\n"       # 9
            "</div>\n"             # 10
        )
        found = self._findings("ln.html", text)
        # 7 is the true line. A strip that dropped the script's newlines instead of
        # blanking them would collapse four lines and report 3.
        self.assertTrue(any("line 7:" in f for f in found), found)
        self.assertFalse(any("line 3:" in f for f in found), found)


class LiveTreeTests(unittest.TestCase):
    def test_repository_is_clean(self):
        """Calibration: a finding here on a clean checkout means the gate is wrong."""
        flagged = [
            (p.relative_to(gate.REPO_ROOT).as_posix(), f)
            for p in gate.iter_templates(gate.SCAN_ROOTS)
            for f in [gate.check(p)]
            if f
        ]
        self.assertEqual(flagged, [], "unbalanced templates: %r" % (flagged[:5],))

    def test_scan_roots_cover_the_served_templates(self):
        names = {p.name for p in gate.iter_templates(gate.SCAN_ROOTS)}
        self.assertIn("backend_dashboard.html", names)
        self.assertIn("portal_base.html", names)

    def test_generated_and_backup_trees_are_out_of_scope(self):
        """docs/generated and var/ hold artifacts and backups, not served templates."""
        paths = [p.as_posix() for p in gate.iter_templates(gate.SCAN_ROOTS)]
        self.assertFalse([p for p in paths if "/docs/generated/" in p])
        self.assertFalse([p for p in paths if "/var/" in p])


if __name__ == "__main__":
    unittest.main()
