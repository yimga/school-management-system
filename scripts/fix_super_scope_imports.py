#!/usr/bin/env python3
"""Repair wave2 import insertions that split multi-line import blocks."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHOOLS = ROOT / "apps" / "schools"

BAD_BLOCK = re.compile(
    r"\nfrom apps\.platform_runtime\.operator_identity import \(\n"
    r"    PLATFORM_SCOPE_[\w,\s]+\n"
    r"    require_platform_scope,\n"
    r"\)\n",
    re.MULTILINE,
)


def _collect_scopes(text: str) -> list[str]:
    return sorted(set(re.findall(r"PLATFORM_SCOPE_\w+", text)))


def _ensure_operator_import(text: str, scopes: list[str]) -> str:
    text = BAD_BLOCK.sub("\n", text)
    block = (
        "from apps.platform_runtime.operator_identity import (\n    "
        + ",\n    ".join(scopes + ["require_platform_scope"])
        + ",\n)\n"
    )
    if block.strip() in text:
        return text
    lines = text.splitlines(keepends=True)
    insert = 0
    in_import = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("from ") or stripped.startswith("import "):
            in_import = True
            insert = i + 1
            continue
        if in_import and stripped and not stripped.startswith("#"):
            break
    lines.insert(insert, block)
    return "".join(lines)


def main() -> int:
    fixed = 0
    for path in sorted(SCHOOLS.glob("super_views*.py")):
        text = path.read_text(encoding="utf-8")
        scopes = _collect_scopes(text)
        if not scopes or "require_platform_scope" not in text:
            continue
        new_text = _ensure_operator_import(text, scopes)
        try:
            ast.parse(new_text)
        except SyntaxError:
            print(f"STILL BROKEN {path.name}")
            continue
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            fixed += 1
            print(f"FIXED {path.name}")
    print(f"fix_super_scope_imports: {fixed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
