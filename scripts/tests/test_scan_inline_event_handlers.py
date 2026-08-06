"""Unit tests for scripts/scan_inline_event_handlers.py (stdlib, no Django).

Locks the M9 CSP-enforce seal's core semantics: it flags a real inline
``on*="..."`` attribute, but NEVER a handler name inside a <script>/<style>
block, a comment, or a look-alike data-attribute; it honors the allow-marker;
it excludes the CSP-bypassed /admin/ surface; and the live template tree is
clean (baseline 0, zero-tolerance).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scan_inline_event_handlers as m  # noqa: E402


class ScanTextTest(unittest.TestCase):
    def _events(self, text):
        return [f["event"] for f in m.scan_text(text, "templates/x.html")]

    def test_flags_inline_onclick(self):
        self.assertEqual(self._events('<button onclick="foo()">x</button>'), ["onclick"])

    def test_flags_multiple_event_kinds(self):
        text = (
            '<select onchange="s()"></select>\n'
            '<form onsubmit="return f()"></form>\n'
            '<input oninput="i()">'
        )
        self.assertEqual(sorted(self._events(text)), ["onchange", "oninput", "onsubmit"])

    def test_ignores_handler_inside_script_block(self):
        # A JS property assignment / string is fine under CSP — it runs inside an
        # already-allowed script, and is not an HTML attribute.
        text = '<script>el.onclick = fn; var s = \'<a onclick="z()">\';</script>'
        self.assertEqual(self._events(text), [])

    def test_ignores_handler_inside_style_block(self):
        self.assertEqual(self._events('<style>/* onclick="x()" */</style>'), [])

    def test_ignores_handler_in_comments(self):
        for comment in (
            '{% comment %}<button onclick="x()">{% endcomment %}',
            '{# <button onclick="x()"> #}',
            '<!-- <button onclick="x()"> -->',
        ):
            self.assertEqual(self._events(comment), [], comment)

    def test_ignores_data_attribute_lookalikes(self):
        # Preceded by a hyphen or a word char, or not a real DOM event: never a handler.
        for html in (
            '<div data-onclick="x">',   # hyphen before "on"
            '<div data-onboarding="1">',  # "on" mid-word
            '<div once="x">',           # not an event name
            '<div data-only="x">',
        ):
            self.assertEqual(self._events(html), [], html)

    def test_allow_marker_same_line_and_line_above(self):
        same = '<button onclick="x()"> <!-- inline-handler-allow: legacy widget -->'
        above = '<!-- inline-handler-allow: legacy widget -->\n<button onclick="x()">'
        self.assertEqual(self._events(same), [])
        self.assertEqual(self._events(above), [])
        # Without the marker it fires.
        self.assertEqual(self._events('<button onclick="x()">'), ["onclick"])


class CollectTempTreeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old_root = m.ROOT
        self._old_roots = m.TEMPLATE_ROOTS
        m.ROOT = self.root
        m.TEMPLATE_ROOTS = [self.root / "templates"]

    def tearDown(self):
        m.ROOT = self._old_root
        m.TEMPLATE_ROOTS = self._old_roots
        self._tmp.cleanup()

    def _write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_admin_surface_is_excluded(self):
        # /admin/ is CSP-bypassed by the middleware, so its handlers are out of scope.
        self._write("templates/admin/index.html", '<button onclick="a()">')
        self._write("templates/portal/page.html", '<button onclick="b()">')
        findings = m.collect()
        files = {f["file"] for f in findings}
        self.assertIn("templates/portal/page.html", files)
        self.assertNotIn("templates/admin/index.html", files)


class LiveTreeCleanTest(unittest.TestCase):
    def test_live_template_tree_has_zero_inline_handlers(self):
        # Zero-tolerance regression seal: the burndown drove the served (non-admin)
        # template surface to 0; a reintroduced inline on*= handler turns this red.
        findings = m.collect()
        self.assertEqual(
            findings,
            [],
            "Inline event handlers reintroduced: "
            + ", ".join(f"{f['file']}:{f['line']} [{f['event']}]" for f in findings),
        )


if __name__ == "__main__":
    unittest.main()
