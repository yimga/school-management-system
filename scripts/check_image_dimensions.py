#!/usr/bin/env python3
"""
Optional CI/pre-commit helper: find <img> tags in templates that lack width/height.
Reduces CLS risk. Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
Exit 0 = all good or no imgs; exit 1 = at least one img missing dimensions.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
IMG_PATTERN = re.compile(
    r"<img\s([^>]*?)>",
    re.IGNORECASE | re.DOTALL,
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Find <img> tags in templates missing width/height (CLS guardrail)."
    )
    p.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (default: this repository root)",
    )
    p.add_argument(
        "--templates",
        type=Path,
        default=TEMPLATES_DIR,
        help="Templates directory to scan (default: <base>/templates)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base_root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"check_image_dimensions: {exc}", file=sys.stderr)
        return 1
    default_tpl = base_root / "templates"
    tpl_dir = (
        default_tpl
        if args.templates == TEMPLATES_DIR
        else (
            args.templates.resolve()
            if args.templates.is_absolute()
            else base_root / args.templates
        )
    )
    if not tpl_dir.is_dir():
        print(
            f"check_image_dimensions: templates path is not a directory: {tpl_dir}",
            file=sys.stderr,
        )
        return 1

    issues: list[tuple[str, str]] = []
    for path in sorted(tpl_dir.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            try:
                rel_err = path.relative_to(base_root)
            except ValueError:
                rel_err = path
            issues.append((str(rel_err), str(e)))
            continue
        rel = path.relative_to(tpl_dir)
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
    raise SystemExit(main(None))
