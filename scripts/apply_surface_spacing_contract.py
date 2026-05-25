#!/usr/bin/env python3
"""Apply workbench marker + compact padding on operational templates."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

ARCHETYPE_RE = re.compile(
    r'(<[^>]+data-page-archetype="operational-workbench")(?=")(?![^>]*data-rmc-operational-workbench)'
)
PY4_RE = re.compile(
    r'(<[^>]+data-page-archetype="operational-workbench"[^>]*class="[^"]*)\bpy-4\b'
)


def patch_file(path: Path) -> tuple[bool, bool]:
    text = path.read_text(encoding="utf-8")
    original = text
    marker_added = False
    py_fixed = False

    if 'data-page-archetype="operational-workbench"' in text:
        if 'data-rmc-operational-workbench="1"' not in text:

            def add_marker(m: re.Match[str]) -> str:
                return m.group(1) + '" data-rmc-operational-workbench="1"'

            new_text, n = ARCHETYPE_RE.subn(add_marker, text, count=1)
            if n:
                text = new_text
                marker_added = True

        if "container-fluid py-4" in text and 'data-rmc-density="open"' not in text:
            new_text, n = PY4_RE.subn(r"\1py-2", text)
            if n:
                text = new_text
                py_fixed = True
            elif "container-fluid py-4" in text:
                text = text.replace("container-fluid py-4", "container-fluid py-2", 1)
                py_fixed = True

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
    return marker_added, py_fixed


def main() -> int:
    markers = py_fixes = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = str(path.relative_to(ROOT))
        if "super_dashboard.html" in rel:
            continue
        m, p = patch_file(path)
        if m:
            markers += 1
        if p:
            py_fixes += 1
    print(f"apply_surface_spacing_contract: markers={markers} py4_to_py2={py_fixes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
