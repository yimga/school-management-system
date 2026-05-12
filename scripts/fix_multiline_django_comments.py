#!/usr/bin/env python3
"""
Convert multi-line Django `{# ... #}` comments to `{% comment %}...{% endcomment %}`.

Django's `{# #}` only supports SINGLE-LINE comments. Multi-line `{# ... #}` blocks
render as literal text in the page output. This script rewrites them safely.

Single-line `{# ... #}` are left untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Match `{#` ... `#}` where the body contains at least one newline (i.e. multi-line).
# Use a tempered token to forbid an intermediate `#}` so we don't cross comments.
MULTILINE_COMMENT = re.compile(
    r"\{#((?:(?!#\}).)*?\n(?:(?!#\}).)*?)#\}",
    re.DOTALL,
)


def convert(text: str) -> tuple[str, int]:
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        body = match.group(1)
        return "{% comment %}" + body + "{% endcomment %}"

    new_text = MULTILINE_COMMENT.sub(repl, text)
    return new_text, count


def main(root: Path) -> int:
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1

    total_files = 0
    total_subs = 0
    for path in sorted(root.rglob("*.html")):
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"skip (encoding): {path}")
            continue
        new_text, n = convert(original)
        if n > 0 and new_text != original:
            path.write_text(new_text, encoding="utf-8")
            total_files += 1
            total_subs += n
            print(f"fixed {n:>3} comment(s): {path.relative_to(root)}")

    print(f"\nDone: {total_subs} multi-line comment(s) converted across {total_files} file(s).")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("templates")
    raise SystemExit(main(target))
