#!/usr/bin/env python3
"""Remove content-max-* width clamps from super_* and control-plane templates."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

PATTERN = re.compile(r"\s*content-max-(?:520|640|960|1200|narrow)\b")


def strip_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    new = PATTERN.sub("", text)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    n = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(TEMPLATES)
        if rel.match("schools/super_*.html"):
            if strip_file(path):
                n += 1
                print("stripped", path.relative_to(ROOT))
            continue
        if "super_" in path.name and path.parent.name == "schools":
            if strip_file(path):
                n += 1
                print("stripped", path.relative_to(ROOT))
            continue
        text = path.read_text(encoding="utf-8")
        if 'extends "control_plane_base"' in text or "extends 'control_plane_base'" in text:
            if strip_file(path):
                n += 1
                print("stripped", path.relative_to(ROOT))
    print(f"strip_super_content_max_classes: {n} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
