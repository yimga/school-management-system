#!/usr/bin/env python3
"""
Wave 4: Replace common inline `style="..."` attributes with utility classes.

Conservative: only replaces styles that match a known pattern exactly, on a
single line, and only inside tags that already have a class= attribute (so we
can append). Skips:
  - email templates (templates/emails/, templates/email/) — emails need inline styles
  - styles that contain template variables (`{{ ... }}` or `{% ... %}`)
  - multi-rule styles where only some rules are mappable (touched: false)

Mappings:
  style="cursor:pointer;"        -> append class "cursor-pointer"
  style="cursor: pointer;"       -> append class "cursor-pointer"
  style="cursor:pointer"         -> append class "cursor-pointer"
  style="white-space: pre-wrap;" -> append class "ws-pre-wrap"
  style="white-space:pre-wrap;"  -> append class "ws-pre-wrap"
  style="display: none;"         -> append class "d-none"
  style="display:none;"          -> append class "d-none"
  style="font-size: 1.5rem;"     -> append class "icon-lg"
  style="font-size:1.5rem;"      -> append class "icon-lg"
  style="max-width: 75%;"        -> append class "max-w-75p"
  style="max-width:75%;"         -> append class "max-w-75p"
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Map a raw style="..." attribute string -> class to append.
# Normalize: strip inner spaces, ensure trailing semicolon for comparison.
STYLE_TO_CLASS = {
    "cursor:pointer": "cursor-pointer",
    "white-space:pre-wrap": "ws-pre-wrap",
    "display:none": "d-none",
    "font-size:1.5rem": "icon-lg",
    "max-width:75%": "max-w-75p",
}


def _normalize_style(value: str) -> str:
    # Collapse all whitespace inside the style; lowercase property names; strip
    # trailing semicolon. Leave URL values etc. alone (none of our targets have them).
    v = value.strip().rstrip(";").strip()
    # Remove all internal whitespace around the colon and semicolons
    v = re.sub(r"\s*([:;])\s*", r"\1", v)
    v = v.lower()
    return v


# Match an element opening tag that contains both class="..." and style="..."
# Capture: full match, class value, style value, and the order they appear.
# Use a non-greedy approach.
TAG_WITH_CLASS_AND_STYLE = re.compile(
    r'(<\w[^>]*?)\bclass="([^"]*)"([^>]*?)\bstyle="([^"]*)"([^>]*?>)',
    re.IGNORECASE,
)
TAG_WITH_STYLE_AND_CLASS = re.compile(
    r'(<\w[^>]*?)\bstyle="([^"]*)"([^>]*?)\bclass="([^"]*)"([^>]*?>)',
    re.IGNORECASE,
)


def _contains_template_expr(s: str) -> bool:
    return "{{" in s or "{%" in s


def _try_swap(class_value: str, style_value: str) -> tuple[str, str] | None:
    """Return (new_class_value, new_style_value_or_empty) if style is fully convertible."""
    if _contains_template_expr(style_value):
        return None
    norm = _normalize_style(style_value)
    if norm in STYLE_TO_CLASS:
        cls = STYLE_TO_CLASS[norm]
        # Avoid duplicating the class.
        existing = class_value.split()
        if cls in existing:
            return class_value, ""
        new_class = (class_value + " " + cls).strip()
        return new_class, ""
    return None


def _rewrite_match_class_first(match: re.Match[str]) -> str:
    pre, cls_val, mid, style_val, post = match.groups()
    swap = _try_swap(cls_val, style_val)
    if swap is None:
        return match.group(0)
    new_cls, new_style = swap
    if new_style:
        return f'{pre}class="{new_cls}"{mid}style="{new_style}"{post}'
    return f'{pre}class="{new_cls}"{mid}{post}'


def _rewrite_match_style_first(match: re.Match[str]) -> str:
    pre, style_val, mid, cls_val, post = match.groups()
    swap = _try_swap(cls_val, style_val)
    if swap is None:
        return match.group(0)
    new_cls, new_style = swap
    if new_style:
        return f'{pre}style="{new_style}"{mid}class="{new_cls}"{post}'
    return f'{pre}{mid}class="{new_cls}"{post}'


def convert(text: str) -> tuple[str, int]:
    before = text
    text = TAG_WITH_CLASS_AND_STYLE.sub(_rewrite_match_class_first, text)
    text = TAG_WITH_STYLE_AND_CLASS.sub(_rewrite_match_style_first, text)
    # Count how many style="..." attributes were removed.
    removed = before.count('style="') - text.count('style="')
    return text, removed


SKIP_DIRS = {"emails", "email"}


def main(root: Path) -> int:
    templates_dir = root / "templates"
    if not templates_dir.is_dir():
        print(f"error: templates dir not found: {templates_dir}", file=sys.stderr)
        return 1

    total_files = 0
    total_subs = 0
    for path in sorted(templates_dir.rglob("*.html")):
        # Skip email templates
        rel_parts = path.relative_to(templates_dir).parts
        if any(p in SKIP_DIRS for p in rel_parts):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text, removed = convert(original)
        if removed > 0 and new_text != original:
            path.write_text(new_text, encoding="utf-8")
            total_files += 1
            total_subs += removed
            print(f"  -{removed:>2} style attr(s)  {path.relative_to(templates_dir)}")

    print(f"\nDone: converted {total_subs} inline style attr(s) across {total_files} file(s).")
    return 0


if __name__ == "__main__":
    project_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    raise SystemExit(main(project_root))
