#!/usr/bin/env python3
"""Convert Django `{# ... #}` comments to `{% comment %}...{% endcomment %}`.

Django only supports single-line `{# #}`; multi-line blocks leak as visible page
text. This codemod eliminates the entire `{# #}` grammar from templates so the
leak class cannot recur.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOTS = [ROOT / "templates", *sorted((ROOT / "apps").glob("*/templates"))]

SINGLE_LINE_HASH = re.compile(r"\{#(?:(?!#\}|\n).)*#\}")
MULTILINE_HASH = re.compile(r"\{#((?:(?!#\}).)*?\n(?:(?!#\}).)*?)#\}", re.DOTALL)


def _convert(text: str) -> tuple[str, int]:
    count = 0

    def repl_single(m: re.Match[str]) -> str:
        nonlocal count
        body = m.group(0)[2:-2].strip()
        count += 1
        return "{% comment %} " + body + " {% endcomment %}"

    def repl_multi(m: re.Match[str]) -> str:
        nonlocal count
        body = m.group(1).strip()
        count += 1
        return "{% comment %} " + body + " {% endcomment %}"

    out = MULTILINE_HASH.sub(repl_multi, text)
    out = SINGLE_LINE_HASH.sub(repl_single, out)
    return out, count


def iter_templates() -> list[Path]:
    out: list[Path] = []
    for root in TEMPLATE_ROOTS:
        if not root.exists():
            continue
        out.extend(sorted(root.rglob("*.html")))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Apply changes")
    parser.add_argument("--paths", nargs="*", help="Optional path subset")
    args = parser.parse_args()

    files = iter_templates()
    if args.paths:
        wanted = {Path(p).as_posix() for p in args.paths}
        files = [p for p in files if p.relative_to(ROOT).as_posix() in wanted]

    total = 0
    changed_files = 0
    for path in files:
        original = path.read_text(encoding="utf-8")
        converted, n = _convert(original)
        if n and converted != original:
            total += n
            changed_files += 1
            rel = path.relative_to(ROOT)
            print(f"{rel}: {n}")
            if args.write:
                path.write_text(converted, encoding="utf-8", newline="\n")

    mode = "wrote" if args.write else "dry-run"
    print(f"codemod_template_hash_to_comment: {mode} {total} comments in {changed_files} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
