#!/usr/bin/env python3
"""Add empty cp_workspace_header block on templates using operational center frame."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
MARKER = '{% include "components/rmc_operational_center_frame.html"'
BLOCK = '{% block cp_workspace_header %}{% endblock %}\n'


def patch(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    if MARKER not in text:
        return False
    if "block cp_workspace_header" in text:
        return False
    if BLOCK.strip() in text:
        return False
    lines = text.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        if "block cp_title" in line:
            insert_at = i + 1
            while insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            break
    if insert_at == 0:
        for i, line in enumerate(lines):
            if "extends " in line:
                insert_at = i + 1
                break
    lines.insert(insert_at, BLOCK)
    path.write_text("".join(lines), encoding="utf-8", newline="\n")
    return True


def main() -> int:
    n = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        if patch(path):
            n += 1
            print("patched", path.relative_to(ROOT))
    print(f"apply_suppress_duplicate_workspace_header: {n} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
