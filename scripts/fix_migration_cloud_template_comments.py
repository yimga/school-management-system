#!/usr/bin/env python3
"""Convert multi-line Django `{# ... #}` blocks to HTML comments (audit-safe)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "templates" / "migration_cloud"

BLOCK = re.compile(r"\{#(.*?)#\}", re.DOTALL)


def _to_html_comment(body: str) -> str:
    collapsed = " ".join(body.split())
    return f"<!-- {collapsed} -->"


def main() -> int:
    changed = 0
    for path in sorted(TARGET.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        new = BLOCK.sub(lambda m: _to_html_comment(m.group(1)), text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
            print(f"fixed {path.relative_to(ROOT)}")
    print(f"done: {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
