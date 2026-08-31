"""A Django ``{# #}`` comment is SINGLE-LINE. A multi-line one renders.

Found 2026-08-31 auditing both admin sites. Django's lexer matches
``{#.*?#}`` WITHOUT re.DOTALL, so a ``{#`` whose ``#}`` sits on a later line is
never tokenised as a comment -- the prose is emitted as literal template text.
Verified against Django itself: ``Template("A{# a\\n b #}B").render()`` returns
``A{# a\\n b #}B``, while the single-line form returns ``AB``.

Two such comments sat inside ``<script type="application/json"
id="rmc-cmdk-data">``. The prose landed mid-array in ``"items": [...]``, so
``JSON.parse`` threw and ``rmc-command-palette.js`` fell into its
``console.warn("invalid #rmc-cmdk-data JSON -- static navigate items
unavailable")`` arm. That island is included by ``admin/base_site.html``,
``base.html``, ``portal_base.html`` and ``control_plane_skeleton.html``, so the
palette silently lost its whole Navigate group on BOTH admin sites, the portal
and the control plane at once.

Static by design: the failure is in the template SOURCE, and a rendered probe
would need a urlconf per host to reach the same bytes.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
TEMPLATES = REPO_ROOT / "templates"
PALETTE = TEMPLATES / "components" / "rmc_command_palette.html"

# a {# ... #} whose closing marker is on a LATER line
# Django's lexer is `{#.*?#}` WITHOUT re.DOTALL, so `.` never crosses a
# newline: a `{#` is a comment only if its `#}` is on the SAME line. Hence the
# detector is "a {# with no #} before end-of-line" -- NOT "a {# whose #} is on
# a later line". The latter reads across unrelated comments and pairs one
# comment's opener with a different comment's closer; it reported 48 templates
# where the honest count is 2.
MULTILINE_HASH = re.compile(r"\{#(?![^\n]*#\})([^\n]*)")
SINGLELINE_HASH = re.compile(r"\{#[^\n]*?#\}")
# {% comment %} discards its BODY too -- verified against Django 2026-08-31:
# Template("A{% comment %}x\ny{% endcomment %}B").render() == "AB". Stripping
# the tags alone (as a naive tag-stripper does) would leave the prose behind
# and report a cured template as still broken.
COMMENT_BLOCK = re.compile(
    r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL
)
ISLAND = re.compile(
    r'<script type="application/json" id="rmc-cmdk-data">(.*?)</script>',
    re.DOTALL,
)


def _multiline_hash_comments(source: str) -> list[str]:
    return MULTILINE_HASH.findall(source)


IF_TAG = re.compile(r"\{%\s*(if|else|elif|endif)\b[^%]*%\}")


def _resolve_conditionals(src: str, taken: bool) -> str:
    """Render every {% if %} as uniformly taken or not, honouring nesting.

    The island's entries are almost all conditional, so JSON validity has to
    hold for the whole lattice of host/permission combinations -- not just the
    one a given render happens to produce. Both extremes are checked; with the
    leading-comma invariant every subset in between follows.
    """
    out, pos, stack = [], 0, []
    for m in IF_TAG.finditer(src):
        kind = m.group(1)
        if not any(skip for _, skip in stack):
            out.append(src[pos:m.start()])
        pos = m.end()
        if kind == "if":
            stack.append((True, not taken))
        elif kind in ("else", "elif"):
            if stack:
                is_if, skip = stack[-1]
                stack[-1] = (is_if, not skip if kind == "else" else not taken)
        elif kind == "endif":
            if stack:
                stack.pop()
    if not any(skip for _, skip in stack):
        out.append(src[pos:])
    return "".join(out)


def _as_django_emits(island: str, taken: bool = True) -> str:
    """Strip exactly what Django strips, keep exactly what it keeps.

    Deliberately does NOT normalise trailing commas. An earlier version did --
    to isolate the comment defect -- and that normalisation hid a SECOND, live
    defect: the `Actions` array ended `{...},` before `]` unconditionally, so
    the island was invalid JSON on every page and every host regardless of the
    comments. Never sand off the very failure mode you are testing for.
    """
    out = COMMENT_BLOCK.sub("", island)            # body discarded, not just tags
    out = SINGLELINE_HASH.sub("", out)             # Django DOES remove these
    out = _resolve_conditionals(out, taken)
    out = re.sub(r"\{%.*?%\}", "", out, flags=re.DOTALL)
    out = re.sub(r"\{\{.*?\}\}", "x", out, flags=re.DOTALL)
    return re.sub(r"\n\s*\n", "\n", out).strip()


class CommandPaletteJsonIslandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PALETTE.read_text(encoding="utf-8", errors="ignore")

    def test_the_palette_template_has_no_multiline_hash_comment(self) -> None:
        found = _multiline_hash_comments(self.source)
        self.assertEqual(
            found,
            [],
            f"{len(found)} multi-line {{# #}} comment(s) in {PALETTE.name}; Django "
            "emits these verbatim. Use {% comment %}...{% endcomment %}",
        )

    def test_the_json_island_parses_whether_or_not_the_options_render(self) -> None:
        match = ISLAND.search(self.source)
        self.assertIsNotNone(match, "the #rmc-cmdk-data island is gone -- renamed?")
        for taken in (True, False):
            with self.subTest(all_conditions=taken):
                blob = _as_django_emits(match.group(1), taken=taken)
                try:
                    json.loads(blob)
                except json.JSONDecodeError as exc:
                    self.fail(
                        f"#rmc-cmdk-data is not valid JSON with all conditions "
                        f"{'true' if taken else 'false'}: {exc.msg} (line "
                        f"{exc.lineno} col {exc.colno}). The palette drops every "
                        "static item on admin, portal and control plane."
                    )

    def test_every_conditional_trailing_comma_is_backstopped(self) -> None:
        """A conditional entry may end in a comma ONLY if one that always
        renders follows it in the same array.

        That is the real invariant, and it is weaker than "never use a trailing
        comma": entries ahead of an unconditional pair are perfectly safe, and a
        blanket ban would demand a reordering of the palette that changes what
        the user sees for no correctness gain. What is NOT safe -- and is what
        actually shipped -- is a conditional (or final unconditional) entry
        with a trailing comma and nothing guaranteed behind it.
        """
        COND_TRAILING = re.compile(
            r"\{%\s*if\b.*?%\}\s*\{\"label\".*\},\s*\{%\s*endif\s*%\}"
        )
        UNCOND_ENTRY = re.compile(r"^\s*\{\"label\"")
        TRAILING_ANY = re.compile(r"\},\s*(\{%\s*endif\s*%\})?\s*$")

        offenders: list[str] = []
        for arm in re.findall(r'"items":\s*\[(.*?)\n\s*\]', self.source, re.DOTALL):
            lines = arm.splitlines()
            entries = [
                (i, ln) for i, ln in enumerate(lines) if '{"label"' in ln
            ]
            for pos, (i, line) in enumerate(entries):
                is_cond = bool(COND_TRAILING.search(line))
                is_last_uncond_trailing = (
                    UNCOND_ENTRY.match(line) and TRAILING_ANY.search(line)
                )
                if not (is_cond or is_last_uncond_trailing):
                    continue
                backstopped = any(
                    UNCOND_ENTRY.match(later) and not COND_TRAILING.search(later)
                    for _, later in entries[pos + 1:]
                )
                if not backstopped:
                    offenders.append(line.strip()[:90])

        self.assertEqual(
            offenders,
            [],
            "entries whose trailing comma can be left stranded before ']':\n  "
            + "\n  ".join(offenders),
        )

    def test_no_template_in_the_repo_has_a_multiline_hash_comment(self) -> None:
        offenders = []
        for path in TEMPLATES.rglob("*.html"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for _ in _multiline_hash_comments(text):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(
            sorted(set(offenders)),
            [],
            f"templates with a multi-line {{# #}} comment: {sorted(set(offenders))}",
        )

    def test_the_detectors_fire_on_a_planted_regression(self) -> None:
        # Both assertions above pass by finding nothing, which is exactly how a
        # broken detector also passes. Plant the real defect and require a catch.
        # catches the real defect
        self.assertEqual(len(_multiline_hash_comments("A{# one\n   two #}B")), 1)
        # and does NOT cry wolf on a legal single-line comment
        self.assertEqual(_multiline_hash_comments("A{# one line #}B"), [])
        # nor on two separate legal comments -- a reader that hunts a later
        # `#}` pairs the first opener with the second closer and reports a
        # phantom. This is the false positive that inflated 2 into 48.
        self.assertEqual(
            _multiline_hash_comments("{# first #}\nfiller\n{# second #}"), []
        )

        island = '{\n "items": [\n  {"a": 1},\n  {# leaked\n     prose #}\n  {"b": 2}\n ]\n}'
        with self.assertRaises(json.JSONDecodeError):
            json.loads(_as_django_emits(island))

        # and the REMEDY actually cures it -- {% comment %} discards the BODY,
        # so a stripper that removed only the tags would leave the prose behind
        # and this would still raise.
        cured = (
            '{\n "items": [\n  {"a": 1},\n'
            "  {% comment %}leaked\n     prose{% endcomment %}\n"
            '  {"b": 2}\n ]\n}'
        )
        json.loads(_as_django_emits(cured))  # must not raise


class TemplateCommentGateRunsToCompletionTests(unittest.TestCase):
    """The gate must NAME its findings, not die printing them.

    ``scripts/verify_template_comment_zero_leak.py`` echoes each offending
    template line. Those lines carry arrows and em dashes, and on a cp1252
    console ``print`` raised UnicodeEncodeError -- the gate emitted 9 of its
    254 findings and then a traceback. A detector that dies mid-report is
    worse than one that stays quiet: the exit code still says 1, so it looks
    like a clean policy failure while most findings were never printed.
    """

    GATE = REPO_ROOT / "scripts" / "verify_template_comment_zero_leak.py"

    def test_the_gate_survives_a_cp1252_console(self) -> None:
        import os
        import subprocess
        import sys

        self.assertTrue(self.GATE.exists(), f"gate missing: {self.GATE}")
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        proc = subprocess.run(
            [sys.executable, str(self.GATE)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, cwd=str(REPO_ROOT),
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        self.assertNotIn(
            "Traceback", combined,
            "the comment gate crashed instead of reporting:\n"
            + combined[-600:],
        )
        self.assertNotIn("UnicodeEncodeError", combined)
        # and it still reaches a verdict line either way
        self.assertRegex(
            combined, r"TEMPLATE_COMMENT_ZERO_LEAK_(PASS|FAIL)",
            "gate produced no verdict line",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
