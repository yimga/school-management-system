"""What each interpolation form actually does to a quote, measured not assumed.

Lane B of the pre-go-live audit was killed before it could confirm its lead:
"{% trans %} output is mark_safe'd rather than escaped, so a translation
containing a double quote breaks the hand-built cmdk JSON island
structurally". Running it settles that the lead is RIGHT, and that the obvious
generalisation of it is WRONG -- which is the whole reason this file exists as
tests rather than as a note.

The island is assembled as TEXT, not by a serializer, and the four forms do
four different things (every row below is asserted, not described):

  {{ var }}                                  autoescaped -> &quot;
                                             island PARSES, user sees mojibake
  {{ var|escapejs }}                         -> \\u0022   CORRECT
  {% trans 'x' %}                            mark_safe   -> raw "
                                             island BREAKS            <-- Lane B
  {% filter escapejs %}{% trans %}{% end %}  -> \\u0022   CORRECT
  {% filter escapejs %}{{ var }}{% end %}    autoescape THEN escapejs
                                             -> \\u0026quot\\u003B, mojibake

So a variable needs the PIPE and a tag needs the BLOCK, and using the block on
a variable is its own bug: it double-escapes. Two live sites had exactly that
in ``rmc_operator_tools_page_data.html`` -- both URLs, where an ``&`` in a
query string would be delivered to the browser as ``&amp;``.

Why any of this is worth a test: the failure is a ``console.warn``, not a 500.
The response is 200, the page renders, the palette is simply empty, and nothing
is logged server-side -- so no status-code sweep or render test can see it. It
is also LOCALE-DEPENDENT: measured at the time of the fix, neither the ``en``
nor the ``fr`` catalog held a quote-bearing translation, so nothing was broken
and English would never have shown it. It fires the day a translator writes
``Aller vers "Accueil"``, which for a bilingual Cameroon deployment is
imminent rather than hypothetical.

``scripts/scan_json_island_escaping.py`` keeps every island escaped across the
tree. This is the behavioural proof underneath it.
"""

from __future__ import annotations

import json
import pathlib
import re

from django.template import Context, Template
from django.test import SimpleTestCase

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PALETTE = REPO_ROOT / "templates" / "components" / "rmc_command_palette.html"

ISLAND = re.compile(
    r'<script type="application/json" id="rmc-cmdk-data">(.*?)</script>',
    re.DOTALL,
)

# A translation a French catalog would plausibly carry. The apostrophe is
# harmless; the double quotes are what close the JSON string.
QUOTED = 'Aller vers "Accueil"'
TRANS_TPL = "{% load i18n %}" + "{% trans 'Aller vers \"Accueil\"' %}"


def _island(fragment: str) -> str:
    """Render one value into a one-key island, the way the templates build it."""
    return Template('{"label": "' + fragment + '"}').render(
        Context({"label": QUOTED})
    )


class JsonIslandEscapingContractTests(SimpleTestCase):
    def test_a_bare_trans_tag_breaks_the_island(self):
        """Lane B's lead, confirmed by running it.

        This is the negative control for every other case here: if it ever
        stops raising, the hazard these tests defend against is gone and they
        are no longer testing anything.
        """
        with self.assertRaises(
            json.JSONDecodeError,
            msg="a quote-bearing {% trans %} must break the island -- "
            "{% trans %} output is mark_safe'd, so autoescape never sees it",
        ):
            json.loads(_island(TRANS_TPL))

    def test_a_bare_variable_survives_but_shows_the_user_mojibake(self):
        """The half of the lead that does NOT generalise.

        A plain variable IS autoescaped, so the island stays parseable -- but
        the label reaches the palette as ``&quot;`` and the user reads the
        entity. Worth asserting precisely because it is the case somebody
        would reasonably assume is also a structural break, and act on wrongly.
        """
        parsed = json.loads(_island("{{ label }}"))
        self.assertEqual(parsed["label"], "Aller vers &quot;Accueil&quot;")
        self.assertNotEqual(
            parsed["label"], QUOTED, "autoescape is no longer applying"
        )

    def test_the_pipe_is_correct_for_a_variable(self):
        parsed = json.loads(_island("{{ label|escapejs }}"))
        self.assertEqual(
            parsed["label"],
            QUOTED,
            "escapejs must survive a round trip -- the label a user reads has "
            "to come back exactly as the translator wrote it",
        )

    def test_the_block_is_correct_for_a_tag(self):
        parsed = json.loads(
            _island("{% filter escapejs %}" + TRANS_TPL + "{% endfilter %}")
        )
        self.assertEqual(parsed["label"], QUOTED)

    def test_the_block_around_a_variable_double_escapes(self):
        """Using the tag remedy on a variable is its own defect.

        The inner ``{{ }}`` is autoescaped FIRST (``"`` -> ``&quot;``) and
        escapejs then encodes the entity, so the value round-trips to the
        entity rather than the character. On a URL that turns ``&`` into
        ``&amp;`` and the link stops working.
        """
        parsed = json.loads(
            _island("{% filter escapejs %}{{ label }}{% endfilter %}")
        )
        self.assertEqual(parsed["label"], "Aller vers &quot;Accueil&quot;")
        self.assertNotEqual(
            parsed["label"],
            QUOTED,
            "if this ever round-trips cleanly, the block-on-a-variable rule "
            "in scan_json_island_escaping.py can be retired",
        )

    def test_a_url_with_a_query_string_is_corrupted_by_the_block(self):
        """The concrete cost, on the shape that actually shipped."""
        url = "https://status.example/incidents?a=1&b=2"
        got = json.loads(
            Template(
                '{"u": "{% filter escapejs %}{{ u }}{% endfilter %}"}'
            ).render(Context({"u": url}))
        )["u"]
        self.assertEqual(got, "https://status.example/incidents?a=1&amp;b=2")

        piped = json.loads(
            Template('{"u": "{{ u|escapejs }}"}').render(Context({"u": url}))
        )["u"]
        self.assertEqual(piped, url, "the pipe must deliver the real URL")

    def test_the_shipped_palette_island_escapes_every_interpolation(self):
        """The real file, not a stand-in.

        ``|safe`` is deliberately accepted: that is the idiom for a value the
        view already serialised with ``json.dumps``, and escaping it again
        would double-encode and break the island.
        """
        source = PALETTE.read_text(encoding="utf-8", errors="ignore")
        match = ISLAND.search(source)
        self.assertIsNotNone(
            match, "the #rmc-cmdk-data island is gone -- renamed?"
        )
        body = match.group(1)

        unescaped = [
            var
            for var in re.findall(r"\{\{\s*(.*?)\s*\}\}", body, re.DOTALL)
            if "escapejs" not in var and "|safe" not in var
        ]
        self.assertEqual(
            unescaped,
            [],
            "unescaped interpolation(s) in the cmdk island: "
            + repr(unescaped)
            + " -- one quote in one translation empties the palette on every "
            "shell that includes it",
        )
