"""The sidebar de-duplicator must not reach outside the sidebar.

Reported repeatedly 2026-08-29..31: the admin model catalog rendered section
headers with real counts over EMPTY bodies, and the app-index rendered cards
carrying only "+ Add" -- no title, no Changelist link. Measured in Chromium:
all 277 catalog tiles were present in the DOM with ``hidden`` set and
``display: none``, and the tile grid had collapsed to ``0px 0px 0px`` columns
because every child was hidden.

``dedupeSidebar`` in ``static/js/rmc-admin-page-aware-v17.js`` hides duplicate
nav links. Two defects made it hide the page instead:

1. It selected ``[data-rmc-shell-sidebar]`` first. That is a shell-ROOT mode
   flag ("offcanvas") set on ``.rmc-app-shell`` by ``_pages/rmc-app-shell.js``
   -- it names the WHOLE PAGE, not the sidebar. On the admin index it matched a
   container holding 693 anchors and all 277 tiles, so the dedupe ran over the
   entire document.
2. It then did ``link.closest("li") || link`` -- with no list ancestor it hid
   the ANCHOR ITSELF. Every catalog tile is an ``<a>`` outside any ``<li>``, so
   each one whose href had appeared earlier on the page was hidden.

That combination explains both reports exactly. On the app-index a card's title
and its "Changelist" link share the SAME href, so Changelist was always a
duplicate of the title and both vanished, while "+ Add" survived because its
href differs.

Static by design: the cascade/DOM question was answered in a browser, and this
pins the two source properties that made it possible, so neither can return.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PAGE_AWARE_JS = REPO_ROOT / "static" / "js" / "rmc-admin-page-aware-v17.js"


def _dedupe_body(source: str) -> str:
    """The text of dedupeSidebar, brace-matched from its declaration."""
    start = source.index("function dedupeSidebar")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError("dedupeSidebar body never closed")


class SidebarDedupeScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PAGE_AWARE_JS.read_text(encoding="utf-8", errors="ignore")
        self.body = _dedupe_body(self.source)

    def test_it_does_not_select_the_shell_root_mode_flag(self) -> None:
        # Comments legitimately NAME the attribute to explain the bug, so look
        # for it in a querySelector call rather than anywhere in the text.
        calls = re.findall(r"querySelector\(\s*[\"'][^\"']*[\"']", self.body)
        offenders = [c for c in calls if "data-rmc-shell-sidebar" in c]
        self.assertEqual(
            offenders,
            [],
            "dedupeSidebar selects the shell-root offcanvas flag, which matches "
            "the whole page: it will hide main-content links again",
        )

    def test_it_never_falls_back_to_hiding_the_anchor(self) -> None:
        self.assertNotIn(
            'closest("li") || link',
            self.body,
            "the anchor fallback hides arbitrary content links that merely "
            "share an href with an earlier one",
        )

    def test_it_bails_out_when_there_is_no_list_item(self) -> None:
        self.assertRegex(
            self.body,
            r"if\s*\(\s*!item\b[^\n]*\)\s*return",
            "without this guard a link with no <li> ancestor is still hidden",
        )

    def test_it_still_targets_a_real_sidebar(self) -> None:
        # The function must keep doing its job; deleting the selector entirely
        # would pass the assertions above while silently retiring the feature.
        self.assertIn("rmc-app-shell__sidebar", self.body)
        self.assertIn("nav-sidebar", self.body)

    def test_the_body_reader_actually_isolates_the_function(self) -> None:
        # Every assertion above is scoped by this helper, so pin it: the body
        # must start at the declaration and must not swallow the whole file.
        self.assertTrue(self.body.startswith("function dedupeSidebar"))
        self.assertTrue(self.body.endswith("}"))
        self.assertLess(len(self.body), len(self.source))
        self.assertNotIn("function wireSaveMenus", self.body)

    def test_the_detectors_fire_on_a_planted_regression(self) -> None:
        # Both assertions pass by NOT finding a string, which is exactly the
        # shape that silently passes when the reader is broken.
        planted = (
            'function dedupeSidebar(root) {\n'
            '  var nav = root.querySelector("[data-rmc-shell-sidebar]");\n'
            '  var item = link.closest("li") || link;\n'
            "}\n"
        )
        body = _dedupe_body(planted)
        calls = re.findall(r"querySelector\(\s*[\"'][^\"']*[\"']", body)
        self.assertTrue([c for c in calls if "data-rmc-shell-sidebar" in c])
        self.assertIn('closest("li") || link', body)
        self.assertNotRegex(body, r"if\s*\(\s*!item\b[^\n]*\)\s*return")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
