#!/usr/bin/env python3
"""Zero-leak gate: no `{# #}` template comments anywhere in the tree.

Multi-line `{# #}` is the root cause of visible header/body comment bleed
(v4.00.23 / v4.00.28 regressions). Platform policy: use `{% comment %}` only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOTS = [ROOT / "templates", *sorted((ROOT / "apps").glob("*/templates"))]

HASH_COMMENT = re.compile(r"\{#")


def iter_templates() -> list[Path]:
    out: list[Path] = []
    for root in TEMPLATE_ROOTS:
        if not root.exists():
            continue
        out.extend(sorted(root.rglob("*.html")))
    return out


def main() -> int:
    findings: list[tuple[str, int, str]] = []
    for path in iter_templates():
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in HASH_COMMENT.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            snippet = text.splitlines()[line - 1].strip()[:120]
            findings.append((path.relative_to(ROOT).as_posix(), line, snippet))

    if findings:
        print("TEMPLATE_COMMENT_ZERO_LEAK_FAIL")
        print(f"  {len(findings)} '{{#' site(s) — use '{{% comment %}}' instead")
        for rel, line, snippet in findings[:40]:
            print(f"  {rel}:{line}  {snippet}")
        if len(findings) > 40:
            print(f"  ... and {len(findings) - 40} more")
        return 1

    print("TEMPLATE_COMMENT_ZERO_LEAK_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
