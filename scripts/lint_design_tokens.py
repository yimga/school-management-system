#!/usr/bin/env python3
"""
Design token lint: flag raw hardcoded colors in dashboard (and optionally admin) templates.
Allowed: var(--...), comments, default fallbacks inside var() e.g. #0f172a in var(--x, #0f172a).
Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
Exit 0 if no violations or --allow-violations; exit 1 and print violations otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories to scan
TEMPLATE_DIRS = [
    "templates/accounts",  # backend_dashboard, profile, etc.
    "templates/portal_base.html",
    "templates/base.html",
]
# Patterns that are allowed (we skip lines matching these)
ALLOWED_PATTERNS = [
    r"var\s*\(\s*--[^)]+\)",  # var(--token) or var(--token, fallback)
    r"\{\{.*\}\}",  # Django template vars
    r"{%\s*",  # Django template tags
    r"^\s*#",  # comment
    r"url\s*\(\s*['\"]",  # url()
]
# Pattern that indicates a potential violation: hex color or rgb( in style/code (we allow if line has var( already)
HEX_OR_RGB = re.compile(
    r"#[0-9a-fA-F]{3}\b|#[0-9a-fA-F]{6}\b|rgb\s*\(|rgba\s*\(", re.IGNORECASE
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def is_allowed(line: str) -> bool:
    for pat in ALLOWED_PATTERNS:
        if re.search(pat, line):
            return True
    if "var(" in line and ("--" in line or "#" in line):
        return True
    return False


def check_file(path: str) -> list[tuple[int, str]]:
    violations = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if is_allowed(line):
                    continue
                # Check for hex or rgb outside var()
                if HEX_OR_RGB.search(line):
                    violations.append((i, line.strip()[:100]))
    except Exception as e:
        violations.append((0, f"Error reading file: {e}"))
    return violations


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint design token usage in templates.")
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (default: this repository root)",
    )
    parser.add_argument(
        "--allow-violations", action="store_true", help="Report only; always exit 0."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_design_tokens: {exc}", file=sys.stderr)
        return 1
    os.chdir(root)
    allow = args.allow_violations
    violations_by_file = {}
    if os.path.isdir("templates/accounts"):
        for name in os.listdir("templates/accounts"):
            if name.endswith(".html"):
                path = os.path.join("templates/accounts", name)
                v = check_file(path)
                if v:
                    violations_by_file[path] = v
    for single in ["templates/portal_base.html", "templates/base.html"]:
        if os.path.isfile(single):
            v = check_file(single)
            if v:
                violations_by_file[single] = v
    if violations_by_file:
        print(
            "Design token lint: potential hardcoded colors (use var(--token) or semantic tokens)"
        )
        for path, vlist in sorted(violations_by_file.items()):
            print(f"  {path}")
            for line_no, snippet in vlist[:10]:
                print(f"    {line_no}: {snippet}")
            if len(vlist) > 10:
                print(f"    ... and {len(vlist) - 10} more")
        if not allow:
            return 1
    print("Design token lint: OK (no violations or --allow-violations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
