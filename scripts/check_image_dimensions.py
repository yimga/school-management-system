#!/usr/bin/env python3
"""
Optional CI/pre-commit helper: find <img> tags in templates that lack width/height.
Reduces CLS risk. Run from repo root: python scripts/check_image_dimensions.py
Exit 0 = all good or no imgs; exit 1 = at least one img missing dimensions.
"""

import re
import sys
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
IMG_PATTERN = re.compile(
    r"<img\s([^>]*?)>",
    re.IGNORECASE | re.DOTALL,
)


def main() -> int:
    issues = []
    for path in sorted(TEMPLATES_DIR.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            issues.append((str(path), str(e)))
            continue
        rel = path.relative_to(TEMPLATES_DIR)
        for m in IMG_PATTERN.finditer(text):
            attrs = m.group(1)
            has_width = "width=" in attrs or "width =" in attrs
            has_height = "height=" in attrs or "height =" in attrs
            if not (has_width and has_height):
                # Allow data: URIs (e.g. QR) or inline SVG to be lenient
                if "data:image" in attrs or 'src=""' in attrs:
                    continue
                issues.append((str(rel), m.group(0).replace("\n", " ")[:80]))
    if not issues:
        print("OK: no <img> tags missing width/height (or none found).")
        return 0
    print("Images missing width/height (add them to reduce CLS):\n")
    for loc, snippet in issues:
        print(f"  {loc}")
        print(f"    {snippet}...")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
