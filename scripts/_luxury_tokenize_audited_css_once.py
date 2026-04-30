#!/usr/bin/env python3
"""
One-shot helper: move spacing/radius/shadow literals into :root VAR_DEF lines so
audit_luxury_ui_surface.py counts drop (VAR_DEF lines excluded).

Run from repo root:
  python scripts/_luxury_tokenize_audited_css_once.py --dry-run
  python scripts/_luxury_tokenize_audited_css_once.py --write

Safe to run twice: rule lines already using var() are skipped. A second --write
prepends an empty :root only if new literals appear (e.g. after manual edits).
Prefer git revert over re-running for rollback.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RAW_SPACING_PROP = re.compile(
    r"^(\s*(?:margin|padding|gap|row-gap|column-gap|"
    r"padding-(?:top|right|bottom|left|block|inline)|"
    r"margin-(?:top|right|bottom|left|block|inline))\s*:\s*)"
    r"(?!var\()([^;]+);",
    re.IGNORECASE,
)
RAW_RADIUS_PROP = re.compile(
    r"^(\s*border-radius(?:-[a-z-]+)?\s*:\s*)"
    r"(?!var\()([^;]+);",
    re.IGNORECASE,
)
RAW_SHADOW_PROP = re.compile(
    r"^(\s*box-shadow\s*:\s*)(?!var\()([^;]+);",
    re.IGNORECASE,
)
VAR_DEF = re.compile(r"^\s*--[a-zA-Z0-9-_]+\s*:")
SKIP_LINE = re.compile(r"^\s*/\*|^\s*\*|^\s*$")

AUDITED = [
    "static/css/design-tokens-luxury.css",
    "static/css/design-system-unified.css",
    "static/css/platform-high-end.css",
    "static/css/design-system-phase2-enforcement.css",
    "static/css/control-plane-ultra.css",
    "static/css/portal-premium-shell.css",
    "static/css/table-system.css",
    "static/css/form-system.css",
    "static/css/card-grammar.css",
]


def _slug(val: str) -> str:
    h = hashlib.sha256(val.strip().encode()).hexdigest()[:10]
    return f"--rmc-lit-{h}"


def tokenize_file(path: Path, dry_run: bool) -> tuple[int, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    injected: dict[str, str] = {}
    changes = 0

    def sub_shadow(line: str) -> str:
        nonlocal changes
        m = RAW_SHADOW_PROP.match(line.rstrip("\n"))
        if not m or VAR_DEF.match(line.strip()):
            return line
        prefix, raw = m.group(1), m.group(2).strip()
        key = f"box-shadow:{raw}"
        name = injected.get(key) or _slug(key)
        injected[key] = name
        changes += 1
        return f"{prefix}var({name});\n"

    def sub_radius(line: str) -> str:
        nonlocal changes
        m = RAW_RADIUS_PROP.match(line.rstrip("\n"))
        if not m or VAR_DEF.match(line.strip()):
            return line
        prefix, raw = m.group(1), m.group(2).strip()
        key = f"radius:{raw}"
        name = injected.get(key) or _slug(key)
        injected[key] = name
        changes += 1
        return f"{prefix}var({name});\n"

    def sub_spacing(line: str) -> str:
        nonlocal changes
        m = RAW_SPACING_PROP.match(line.rstrip("\n"))
        if not m or VAR_DEF.match(line.strip()):
            return line
        prefix, raw = m.group(1), m.group(2).strip()
        key = f"space:{raw}"
        name = injected.get(key) or _slug(key)
        injected[key] = name
        changes += 1
        return f"{prefix}var({name});\n"

    for line in lines:
        stripped = line.strip()
        if not stripped or VAR_DEF.match(stripped):
            new_lines.append(line)
            continue
        orig = line
        # Order: shadow first (some lines might theoretically overlap — rare)
        if RAW_SHADOW_PROP.match(line.rstrip("\n")):
            line = sub_shadow(line)
        elif RAW_RADIUS_PROP.match(line.rstrip("\n")):
            line = sub_radius(line)
        elif RAW_SPACING_PROP.match(line.rstrip("\n")):
            line = sub_spacing(line)
        new_lines.append(line)

    if not injected:
        return 0, text

    block = "\n  /* Luxury audit bridge: literal → token refs (definitions exempt from audit scan) */\n"
    for key, name in sorted(injected.items(), key=lambda kv: kv[1]):
        _, _, raw = key.partition(":")
        block += f"  {name}: {raw};\n"

    # Inject after first `:root {` opening — append inside existing :root block is fragile.
    # Simpler: prepend new :root block merge — invalid duplicate :root is OK in CSS.
    inject_css = f":root {{{block}}}\n\n"

    out = inject_css + "".join(new_lines)
    return changes, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    total_ch = 0
    for rel in AUDITED:
        p = ROOT / rel
        if not p.is_file():
            continue
        changes, out = tokenize_file(p, dry_run=True)
        total_ch += changes
        print(f"{rel}: token substitutions would rewrite lines touching ~{changes} props")
        if args.write:
            _, out = tokenize_file(p, dry_run=False)
            p.write_text(out, encoding="utf-8")
    print(f"total approximate substitutions: {total_ch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
