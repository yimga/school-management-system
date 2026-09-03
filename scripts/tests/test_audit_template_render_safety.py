"""A <script type="application/json"> island IS Django template territory.

The gate masked every <script> body before scanning, on the reasoning that
inline JS is not template syntax. That is true of executable JS and false of a
JSON data island, which is assembled from {% if %} / {% url %} / {% trans %}
and rendered by Django like any other markup.

The consequence, found 2026-08-31: two multi-line ``{# ... #}`` comments sat
inside ``<script type="application/json" id="rmc-cmdk-data">`` in
templates/components/rmc_command_palette.html. Django's lexer is ``{#.*?#}``
WITHOUT re.DOTALL, so neither was a comment -- the prose rendered into the
middle of a JSON array and the command palette silently lost every static item
on both admin sites, the portal and the control plane. This gate is the one
written to catch exactly that, and it reported 0 findings the whole time,
because the island was masked before it ever looked.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_template_render_safety as gate  # noqa: E402


class JsonIslandIsScannedTests(unittest.TestCase):
    def test_a_multiline_hash_comment_inside_a_json_island_is_found(self) -> None:
        html = (
            '<div>ok</div>\n'
            '<script type="application/json" id="x">{\n'
            '  "items": [\n'
            '  {# leaked\n'
            '     prose #}\n'
            '  {"a": 1}\n'
            '  ]\n'
            '}</script>\n'
        )
        found = gate.find_token_leaks(html)
        self.assertTrue(
            any("multi-line" in msg for _, msg in found),
            f"the JSON island was masked, so the defect is invisible: {found}",
        )

    def test_executable_js_is_still_masked(self) -> None:
        # Inline JS legitimately carries }} and ${...}; flagging it is the noise
        # that gets a zero-tolerance gate switched off.
        html = (
            "<script>\n"
            "  const t = `${a}` ;\n"
            "  const o = {x: {y: 1}} ;\n"
            "</script>\n"
        )
        self.assertEqual(
            gate.find_token_leaks(html), [], "executable JS must stay masked"
        )

    def test_alpine_attribute_braces_are_not_leaks(self) -> None:
        html = '<div x-data="{ open: false }">hi</div>\n'
        self.assertEqual(gate.find_token_leaks(html), [])

    def test_a_tag_abutting_a_json_brace_is_not_an_orphan(self) -> None:
        # `{% endif %}}` is a tag plus the `}` closing a JSON object. A scan that
        # has not masked tags first reads the final two characters as `}}`.
        # This is the false positive unmasking the islands made reachable.
        html = (
            '<script type="application/json" id="c">'
            '{"auto":{% if flag %}true{% else %}false{% endif %}}'
            "</script>\n"
        )
        self.assertEqual(
            gate.find_token_leaks(html),
            [],
            "`{% endif %}` followed by a JSON `}` is not an orphan `}}`",
        )

    def test_a_real_orphan_is_still_reported(self) -> None:
        # The masking above must not blind the check it protects.
        self.assertTrue(
            any("orphan" in m for _, m in gate.find_token_leaks("<p>}} alone</p>\n")),
            "a genuinely stray }} must still be reported",
        )
        self.assertTrue(
            any("orphan" in m for _, m in gate.find_token_leaks("<p>{{ alone</p>\n"))
        )

    def test_the_live_palette_template_is_clean(self) -> None:
        # Regression seal on the file that shipped the defect.
        palette = (
            SCRIPTS.parent
            / "templates"
            / "components"
            / "rmc_command_palette.html"
        )
        if not palette.exists():  # pragma: no cover - renamed
            self.skipTest(f"{palette} not present")
        text = palette.read_text(encoding="utf-8", errors="ignore")
        self.assertEqual(
            gate.find_token_leaks(text),
            [],
            "the command-palette template leaks template tokens again",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
