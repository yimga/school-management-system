"""A template tag that spans a newline is not a tag -- Django prints it.

``django.template.base.tag_re`` is::

    re.compile(r"({%.*?%}|{{.*?}}|{#.*?#})")

with no ``re.DOTALL``, so ``.`` never matches a newline and a tag broken across
lines is not tokenised as a tag at all. It stays a TextNode, and Django renders
the tag's own source onto the page.

Measured before this gate existed: seven live ones, every one an
``{% include "components/rmc_empty_state.html" with ... %}`` broken across lines
for readability. So on six user-facing surfaces -- the teacher timetable, the
data-quality centre, payment-readiness setup, the configure hub, the report
library and the notifications panel -- an empty list rendered the literal text
``{% include "components/rmc_empty_state.html" with icon="bi-inbox" ... %}``
instead of the empty-state card. The failure appears only when a list is empty,
which is exactly when a user is most likely to be lost.

Six more sit inside ``{% comment %}`` blocks as usage documentation for their own
component. Those never render and stay readable; they are exempt.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.template.base import tag_re
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]

# A tag opener with a newline before its closer.
MULTILINE = re.compile(r"\{%(?:[^%]|%(?!\}))*?\n(?:[^%]|%(?!\}))*?%\}", re.S)
EMITS_TAG = re.compile(r"\{%\s*\w+")


def _template_files():
    roots = [ROOT / "templates"]
    roots += [
        p / "templates" for p in (ROOT / "apps").iterdir() if (p / "templates").is_dir()
    ]
    for base in roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.html")):
            yield path


def _inside_comment(source: str, at: int) -> bool:
    before = source[:at]
    return before.count("{% comment %}") > before.count("{% endcomment %}")


class TemplateTagsAreSingleLineTests(SimpleTestCase):
    def test_django_still_lexes_tags_without_dotall(self):
        """The premise, asserted rather than assumed.

        If a future Django adds re.DOTALL here, the rule below stops being a
        correctness gate and becomes a style preference -- and whoever meets it
        should be told that rather than left guessing.
        """
        self.assertFalse(
            tag_re.flags & re.DOTALL,
            "django.template.base.tag_re now sets re.DOTALL: a multi-line tag "
            "may lex correctly, and this gate needs revisiting.",
        )

    def test_no_live_tag_spans_a_newline(self):
        offenders = []
        for path in _template_files():
            source = path.read_text(encoding="utf-8", errors="replace")
            for match in MULTILINE.finditer(source):
                if _inside_comment(source, match.start()):
                    continue
                line = source[: match.start()].count("\n") + 1
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                collapsed = " ".join(match.group(0).split())[:90]
                offenders.append(f"{rel}:{line}  {collapsed}")
        self.assertEqual(
            offenders,
            [],
            "Template tag(s) broken across lines. Django will not lex these; it "
            "renders their source onto the page. Put each tag on one line:\n  "
            + "\n  ".join(offenders),
        )

    def test_no_template_emits_a_template_tag_as_text(self):
        """The same defect asked of the ENGINE rather than of the bytes.

        Catches any other way a tag can end up as visible text, not only a
        stray newline.
        """
        from apps.siteconfig.tests._template_nodes import literal_text

        offenders = []
        for path in _template_files():
            try:
                emitted = literal_text(path)
            except Exception:  # noqa: BLE001 - an unparseable template is another gate's job
                continue
            match = EMITS_TAG.search(emitted)
            if match:
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                sample = emitted[match.start() : match.start() + 80]
                offenders.append(f"{rel}  emits {sample!r}")
        self.assertEqual(
            offenders,
            [],
            "Template(s) that render a template tag as visible text:\n  "
            + "\n  ".join(offenders),
        )
