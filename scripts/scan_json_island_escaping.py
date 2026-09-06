#!/usr/bin/env python3
"""Every interpolation inside a hand-built JSON <script> island must be escaped.

A JSON island is assembled as TEXT, not built by a serializer, so a value carrying
a double quote, a backslash or a newline closes the JSON string early and the
island stops parsing. **The failure is a console.warn, not a 500** -- the page
renders, the response is 200, and one feature is simply dead. Nothing in a
status-code sweep, a render test, or a template-compile check can see it.

Introduced 2026-09-05 after an audit of the cmdk command palette. 169 unescaped
interpolations were live across 27 templates, including
``templates/components/rmc_command_palette.html`` -- so a single translated string
containing a quote would have emptied the command palette on every shell, in that
locale only. Measured at the time: the ``fr`` and ``en`` catalogs contained ZERO
quote-bearing translations, so nothing was broken yet. That is a tripwire under a
bilingual rollout, not an outage, and it is exactly the kind of thing that goes
off the day a translator does their job.

THE FIX IS ALREADY IN THE REPO. ``templates/partials/rmc_shortcuts_i18n.html``
wraps every string in ``{% filter escapejs %}``; that is the pattern.

    {% trans "x" %}   ->  {% filter escapejs %}{% trans "x" %}{% endfilter %}
    {{ var }}         ->  {{ var|escapejs }}

A TAG needs the BLOCK and a VARIABLE needs the PIPE, and they are not
interchangeable. Measured against Django (see
``apps/siteconfig/tests/test_json_island_escaping_2026_09_06.py``, which
asserts every row):

    {{ var }}                                autoescaped -> &quot;
                                             island parses, user sees mojibake
    {% trans 'x' %}                          mark_safe -> raw quote -> BREAKS
    {% filter escapejs %}{{ var }}{% end %}  autoescape THEN escapejs
                                             -> \\u0026quot -- DOUBLE

That last row is why this gate reports over-escaping too. A variable wrapped
in the block is autoescaped FIRST, so the value round-trips to the HTML
entity rather than the character -- and on a URL it turns ``&`` into
``&amp;`` and the link stops working. Two live sites had exactly that in
``templates/partials/rmc_operator_tools_page_data.html``, both URLs, and
neither was visible to the unescaped check: they were escaped, just twice.
``{% blocktrans %}`` is exempt -- its ``{{ }}`` are placeholders in the
msgid, not standalone interpolations.

DELIBERATELY OUT OF SCOPE: ``{{ var|safe }}``. That is the idiom for a value the
view already serialised with ``json.dumps``, which is raw JSON on purpose --
escaping it would double-encode and break the island. All 13 such sites were read
at introduction and every one is ``json.dumps(...)`` output (see
``apps/compliance/views_dashboard.py``). Flagging them would bury the real
findings under correct code, which is how a gate gets switched off.

Zero-tolerance: NO baseline JSON. An unescaped interpolation in a JSON island is
never intentional.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ISLAND = re.compile(
    r"<script[^>]*type\s*=\s*[\"']application/json[\"'][^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)
SAFE_BLOCK = re.compile(
    r"\{%\s*filter\s+[^%]*escapejs[^%]*%\}.*?\{%\s*endfilter\s*%\}", re.DOTALL
)
# Same span as SAFE_BLOCK, but capturing the BODY so it can be inspected
# for over-escaping.
SAFE_BLOCK_BODY = re.compile(
    r"\{%\s*filter\s+[^%]*escapejs[^%]*%\}(.*?)\{%\s*endfilter\s*%\}", re.DOTALL
)
BLOCKTRANS = re.compile(
    r"\{%\s*blocktrans\b.*?%\}.*?\{%\s*endblocktrans\s*%\}", re.DOTALL
)
TRANS = re.compile(r"\{%\s*(?:trans|blocktrans)\b.*?%\}")
VAR = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
ALLOW = re.compile(r"\{#\s*json-island-allow:\s*(\S+(?:[ -]\S+){2,})\s*#\}")

# A trailing filter that makes the value safe to drop into a JSON island.
SAFE_FILTERS = ("escapejs", "json_script", "safe")


def _blank(m: re.Match) -> str:
    return " " * len(m.group(0))


def unescaped(body: str) -> list[str]:
    """Interpolations in `body` not covered by an escaping wrapper."""
    guarded = SAFE_BLOCK.sub(_blank, body)
    bad: list[str] = []
    for m in TRANS.finditer(guarded):
        bad.append(m.group(0).strip())
    for m in VAR.finditer(guarded):
        expr = m.group(1)
        tail = expr.split("|")[-1].strip().split(":")[0].strip()
        if "|" in expr and tail in SAFE_FILTERS:
            continue
        bad.append(m.group(0).strip())
    return bad


def double_escaped(body: str) -> list[str]:
    """Variables sitting inside a ``{% filter escapejs %}`` block.

    The block is the remedy for a TAG. Applied to a variable it escapes twice:
    autoescape runs first and turns the character into an HTML entity, then
    escapejs encodes the entity. The island still parses, so the unescaped
    check stays green while the user reads ``&quot;`` -- or, on a URL, follows
    a link whose ``&`` became ``&amp;``.

    ``{% blocktrans %}`` placeholders are not standalone interpolations and are
    not findings.
    """
    bad: list[str] = []
    for m in SAFE_BLOCK_BODY.finditer(body):
        inner = BLOCKTRANS.sub(_blank, m.group(1))
        for v in VAR.finditer(inner):
            bad.append(v.group(0).strip())
    return bad


def scan(paths: list[Path]) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for p in paths:
        try:
            text = p.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        if "application/json" not in text:
            continue
        if ALLOW.search(text):
            continue
        for m in ISLAND.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            rel = p.relative_to(ROOT).as_posix()
            for frag in unescaped(m.group(1)):
                out.append((rel, line, "unescaped: " + frag[:78]))
            for frag in double_escaped(m.group(1)):
                out.append((rel, line, "double-escaped: " + frag[:74]))
    return out


def self_check() -> bool:
    """A scan never shown finding anything is not evidence that it found nothing."""
    cases = [
        ('<script type="application/json">{"a": "{% trans "Hi" %}"}</script>', 1),
        (
            '<script type="application/json">{"a": "{% filter escapejs %}'
            "{% trans \"Hi\" %}{% endfilter %}\"}</script>",
            0,
        ),
        ('<script type="application/json">{"a": "{{ v|escapejs }}"}</script>', 0),
        ('<script type="application/json">{"a": {{ v|safe }}}</script>', 0),
        ('<script type="application/json">{"a": "{{ v }}"}</script>', 1),
    ]
    ok = True
    # Over-escaping: same island, escaped twice. The unescaped check is blind
    # to these by construction -- they ARE escaped.
    double_cases = [
        (
            '<script type="application/json">{"a": "{% filter escapejs %}'
            '{{ v }}{% endfilter %}"}</script>',
            1,
        ),
        (
            '<script type="application/json">{"a": "{% filter escapejs %}'
            '{% trans "Hi" %}{% endfilter %}"}</script>',
            0,
        ),
        (
            '<script type="application/json">{"a": "{% filter escapejs %}'
            '{% blocktrans %}Hi {{ name }}{% endblocktrans %}{% endfilter %}"}'
            "</script>",
            0,
        ),
    ]
    for src, want in double_cases:
        m = ISLAND.search(src)
        got = len(double_escaped(m.group(1))) if m else -1
        if got != want:
            print(f"SELF-CHECK FAIL (double): expected {want}, got {got}")
            ok = False
    for src, want in cases:
        m = ISLAND.search(src)
        got = len(unescaped(m.group(1))) if m else -1
        if got != want:
            print(f"SELF-CHECK FAIL: expected {want}, got {got} for: {src[:60]}")
            ok = False
    # A non-JSON <script> must never be inspected.
    if ISLAND.search('<script>var x = "{% trans "Hi" %}";</script>'):
        print("SELF-CHECK FAIL: matched a non-JSON script tag")
        ok = False
    return ok


def main() -> int:
    if "--self-check" in sys.argv or True:
        if not self_check():
            print("DETECTOR IS BROKEN -- refusing to report a result.")
            return 2
    files = [
        ROOT / rel
        for rel in subprocess.run(
            ["git", "ls-files", "*.html"], cwd=ROOT,
            capture_output=True, text=True, check=False,
        ).stdout.splitlines()
        if rel.strip()
    ]
    if not files:
        print("EMPTY CORPUS -- a zero here would be meaningless.")
        return 2
    findings = scan(files)
    print(f"json-island-escaping: {len(files)} templates, {len(findings)} findings")
    for rel, line, frag in findings[:50]:
        print(f"  {rel}:{line}  {frag}")
    if findings:
        print(
            "\nWrap it: {% filter escapejs %}...{% endfilter %} for a tag, "
            "|escapejs for a variable. See templates/partials/rmc_shortcuts_i18n.html."
        )
        return 1
    print("JSON_ISLAND_ESCAPING_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
