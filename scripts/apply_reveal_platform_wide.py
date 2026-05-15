#!/usr/bin/env python3
"""v2.28 — apply `.rmc-reveal` to every below-fold section platform-wide.

Strategy:
  - For each template under `templates/` (excluding partials, components,
    errors, emails, admin third-party, unfold third-party):
      - Find every `<section ...>` and `<article ...>` opening tag
      - SKIP the first one in the file (heuristic: above-fold / hero)
      - For each remaining one, add `rmc-reveal` to its class list
        (creating the attribute if absent)
      - Idempotent: skip if `rmc-reveal` already present

Why skip the first occurrence: above-the-fold content should appear immediately
on page paint; reveal fade-up is only appropriate for content the reader
scrolls into. Apple's own marketing surface follows this same pattern.

Files that have `data-mkt-reveal` (existing marketing reveal attribute) on the
section also get `rmc-reveal` because the two systems compose — `data-mkt-reveal`
is a parallax data hint, `rmc-reveal` is the actual fade-up class.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"

EXCLUDE_DIR_PARTS = {
    "partials",
    "components",
    "errors",
    "emails",
    "admin",
    "unfold",
}

# Match opening <section ...> or <article ...> tag. Capture the tag name
# and the attribute block so we can rewrite it.
SECTION_OPEN = re.compile(
    r"<(section|article|aside)(\s[^>]*)?>",
    re.IGNORECASE,
)

CLASS_ATTR = re.compile(r'\bclass\s*=\s*(["\'])([^"\']*?)\1', re.IGNORECASE)


def _path_is_partial(p: Path) -> bool:
    return any(part in EXCLUDE_DIR_PARTS for part in p.parts)


def _add_reveal_class(tag_attrs: str) -> str:
    """Add `rmc-reveal` to the class list inside the tag's attribute block."""
    cm = CLASS_ATTR.search(tag_attrs)
    if cm:
        existing_classes = cm.group(2)
        if re.search(r"\brmc-reveal\b", existing_classes):
            return tag_attrs  # already revealed
        new_classes = (existing_classes + " rmc-reveal").strip()
        return tag_attrs[: cm.start(2)] + new_classes + tag_attrs[cm.end(2):]
    # No class attribute at all — append one.
    return tag_attrs + ' class="rmc-reveal"'


def rewrite_file(text: str) -> tuple[str, int]:
    pieces: list[str] = []
    last = 0
    seen = 0
    changes = 0
    for m in SECTION_OPEN.finditer(text):
        pieces.append(text[last : m.start()])
        seen += 1
        attrs = m.group(2) or ""
        # Heuristic: above-fold is the FIRST section/article in the file.
        if seen == 1:
            pieces.append(m.group(0))
        else:
            new_attrs = _add_reveal_class(attrs)
            if new_attrs != attrs:
                changes += 1
                pieces.append(f"<{m.group(1)}{new_attrs}>")
            else:
                pieces.append(m.group(0))
        last = m.end()
    pieces.append(text[last:])
    return "".join(pieces), changes


def main() -> int:
    files_changed = 0
    total_reveals = 0
    for p in sorted(TEMPLATES_ROOT.rglob("*.html")):
        if _path_is_partial(p):
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new, n = rewrite_file(src)
        if n:
            p.write_text(new, encoding="utf-8")
            files_changed += 1
            total_reveals += n
    print(f"Files changed: {files_changed}")
    print(f"Sections / articles revealed: {total_reveals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
