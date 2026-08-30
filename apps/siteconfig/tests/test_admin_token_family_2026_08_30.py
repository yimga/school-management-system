"""The admin colour tokens are a FAMILY: a block declaring one declares them all.

`--admin-muted` was the only member of {surface, text, muted, border} with no
home in design-tokens.css. It therefore resolved EMPTY on the admin shell
(measured in Chromium 2026-08-29), and an unguarded ``color: var(--admin-muted)``
resolves to nothing at computed-value time -- the declaration collapses and the
element silently inherits whatever colour the surrounding shell set. That is the
same failure a peer fixed for ``--rmc-admin-text`` in 555a756b6, whose commit
message describes it exactly: "resolved to nothing and the declaration collapsed".

Static by design. The cascade question -- which rule WINS -- can only be answered
by a browser, and is not what this pins. This pins the cheaper invariant that
makes the collapse impossible in the first place: the token has a value to find.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
TOKENS_CSS = REPO_ROOT / "static" / "css" / "design-tokens.css"

# The text pair. surface/border are declared alongside them and are checked as
# context, but text+muted are the pair that must never split: a shell with text
# and no muted is exactly the state that collapses.
TEXT_PAIR = ("--admin-text", "--admin-muted")


def _strip_comments(source: str) -> str:
    """Blank out /* */ comments, preserving line count.

    A brace inside a comment is not a block. design-tokens.css contains both
    ``--ds-{success,danger,info}`` and this fix's own ``{surface,text,border}``
    in prose, and a reader that walks back to the nearest ``{`` attributes the
    declarations after them to a sentence. That is not hypothetical: it split
    this very family across two phantom blocks on the first run.
    """
    out = []
    depth = 0
    i = 0
    while i < len(source):
        if source.startswith("/*", i):
            depth += 1
            out.append("  ")
            i += 2
        elif source.startswith("*/", i) and depth:
            depth -= 1
            out.append("  ")
            i += 2
        else:
            ch = source[i]
            out.append(ch if (depth == 0 or ch == "\n") else " ")
            i += 1
    return "".join(out)


def _blocks_declaring(source: str, token: str) -> set[str]:
    """Selectors of every block declaring ``token``."""
    lines = _strip_comments(source).splitlines()
    found: set[str] = set()
    for i, line in enumerate(lines):
        if not re.match(rf"^\s*{re.escape(token)}\s*:", line):
            continue
        for j in range(i - 1, -1, -1):
            if "{" in lines[j]:
                found.add(lines[j].split("{")[0].strip())
                break
    return found


class AdminTokenFamilyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.css = TOKENS_CSS.read_text(encoding="utf-8", errors="ignore")

    def test_every_block_declaring_admin_text_also_declares_admin_muted(self) -> None:
        text_blocks = _blocks_declaring(self.css, "--admin-text")
        muted_blocks = _blocks_declaring(self.css, "--admin-muted")
        self.assertTrue(text_blocks, "--admin-text is not declared at all")
        orphaned = sorted(text_blocks - muted_blocks)
        self.assertEqual(
            orphaned,
            [],
            "blocks declaring --admin-text but NOT --admin-muted: "
            f"{orphaned} -- an unguarded var(--admin-muted) there collapses "
            "and inherits the shell's colour",
        )

    def test_the_pair_is_declared_for_both_light_and_dark(self) -> None:
        # One shared declaration would leave the other theme reading the wrong
        # end of the ramp, which is how a muted token becomes unreadable rather
        # than merely absent.
        for token in TEXT_PAIR:
            with self.subTest(token=token):
                self.assertGreaterEqual(
                    len(_blocks_declaring(self.css, token)),
                    2,
                    f"{token} is declared in fewer than two blocks, so one "
                    "theme inherits the other's value",
                )

    def test_the_block_reader_actually_finds_a_known_declaration(self) -> None:
        # Both assertions above pass by comparing sets this helper produced, so
        # pin it against a declaration known to exist and a token known not to.
        self.assertTrue(
            _blocks_declaring(self.css, "--admin-text"),
            "reader found no --admin-text block; the assertions above are vacuous",
        )
        self.assertEqual(
            _blocks_declaring(self.css, "--admin-definitely-not-a-token"),
            set(),
            "reader invented a block for a token that does not exist",
        )

    def test_a_brace_inside_a_comment_is_not_a_block(self) -> None:
        # The bug this helper actually shipped with: prose containing a brace
        # became the "selector" for every declaration after it, splitting one
        # real block into two phantoms and failing a correct tree.
        sample = (
            ":root {\n"
            "  /* mentions --ds-{success,danger} in prose */\n"
            "  --admin-text: #000;\n"
            "  --admin-muted: #444;\n"
            "}\n"
        )
        self.assertEqual(
            _blocks_declaring(sample, "--admin-text"),
            _blocks_declaring(sample, "--admin-muted"),
            "a brace in a comment split one block into two",
        )
        self.assertEqual(_blocks_declaring(sample, "--admin-text"), {":root"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
