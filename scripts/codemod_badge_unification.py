#!/usr/bin/env python3
"""Wave C codemod: fold Bootstrap badge dialects onto the .rmc-badge grammar.

Rewrites `class="..."` attributes that use a `badge` flavour (BS5 `bg-*`,
`text-bg-*`, deprecated BS4 `badge-*`, or `*-subtle text-*-emphasis`) into the
canonical `.rmc-badge` + semantic modifier. Other utility classes (spacing,
font weight, etc.) are preserved.

SAFETY:
  * Only touches a class attribute when a standalone `badge` token is present
    AND `rmc-badge` is not already there.
  * SKIPS any class attribute containing template logic (`{%`/`{{`) — a
    conditional class would be mangled; those are reported, not rewritten.
  * SKIPS the 4 shared shells, /email/ (no external CSS in mail), and
    /marketing/ (separate design language + bundle).
  * An unrecognised badge colour is left untouched and reported.

Usage:
  python scripts/codemod_badge_unification.py            # dry-run + report
  python scripts/codemod_badge_unification.py --apply    # write changes
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"

EXCLUDE_FILES = {
    "templates/base.html",
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/admin/base_site.html",
}
EXCLUDE_DIR_PARTS = ("/email/", "/marketing/")

# colour signal token-sets, highest priority first
TONE_SIGNALS = [
    ("danger",  {"bg-danger", "text-bg-danger", "badge-danger", "bg-danger-subtle", "text-bg-danger-subtle"}),
    ("warning", {"bg-warning", "text-bg-warning", "badge-warning", "bg-warning-subtle", "text-bg-warning-subtle"}),
    ("success", {"bg-success", "text-bg-success", "badge-success", "bg-success-subtle", "text-bg-success-subtle"}),
    ("info",    {"bg-info", "text-bg-info", "badge-info", "bg-info-subtle", "text-bg-info-subtle"}),
    ("brand",   {"bg-primary", "text-bg-primary", "badge-primary", "bg-primary-subtle", "text-bg-primary-subtle"}),
    ("muted",   {"bg-light", "text-bg-light", "badge-light", "bg-light-subtle", "text-bg-light-subtle"}),
    ("neutral", {"bg-secondary", "text-bg-secondary", "badge-secondary", "bg-secondary-subtle", "text-bg-secondary-subtle"}),
]
ALL_SIGNALS = {tok for _, s in TONE_SIGNALS for tok in s}
# paired text utilities a badge uses purely for contrast — rmc-badge owns colour
TEXT_DROP = {"text-dark", "text-white", "text-light", "text-black", "text-muted"}
EMPHASIS_RE = re.compile(r"^text-(success|warning|danger|info|primary|secondary|light)-emphasis$")

MOD = {
    "danger": "rmc-badge--danger",
    "warning": "rmc-badge--warning",
    "success": "rmc-badge--success",
    "info": "rmc-badge--info",
    "brand": "rmc-badge--brand",
    "muted": "rmc-badge--muted",
    "neutral": "",  # base .rmc-badge is neutral
}

CLASS_ATTR = re.compile(r"""class=(?P<q>["'])(?P<val>.*?)(?P=q)""", re.DOTALL)


def transform_class(val: str) -> tuple[str | None, str]:
    """Return (new_value_or_None, status). None means leave unchanged."""
    if "{%" in val or "{{" in val:
        return None, "skip-template-logic"
    tokens = val.split()
    if "badge" not in tokens or any(t == "rmc-badge" or t.startswith("rmc-badge--") for t in tokens):
        return None, "skip-not-badge-or-already"

    has_pill = "rounded-pill" in tokens
    tone = None
    present = set(tokens)
    for name, sig in TONE_SIGNALS:
        if present & sig:
            tone = name
            break

    # an unrecognised colour (e.g. bg-dark, a brand-custom class) → don't guess
    leftover_bg = [t for t in tokens if (t.startswith("bg-") or t.startswith("text-bg-")
                   or (t.startswith("badge-") and t != "badge")) and t not in ALL_SIGNALS]
    if tone is None and leftover_bg:
        return None, "skip-unknown-colour:" + ",".join(leftover_bg)
    if tone is None:
        tone = "neutral"

    # count pill idiom: solid brand pill wrapping a numeric → emphasis count
    modifier = MOD[tone]
    if tone == "brand" and has_pill:
        modifier = "rmc-badge--count"

    out: list[str] = ["rmc-badge"]
    if modifier:
        out.append(modifier)
    for t in tokens:
        if t == "badge" or t in ALL_SIGNALS or t in TEXT_DROP or t == "rounded-pill":
            continue
        if EMPHASIS_RE.match(t):
            continue
        out.append(t)
    return " ".join(out), "rewrite:" + tone + ("+count" if modifier == "rmc-badge--count" else "")


def process(text: str) -> tuple[str, int, list[str]]:
    changed = 0
    notes: list[str] = []

    def repl(m: re.Match) -> str:
        nonlocal changed
        new_val, status = transform_class(m.group("val"))
        if status.startswith("skip-unknown-colour"):
            notes.append(status)
        if new_val is None:
            return m.group(0)
        changed += 1
        return f'class={m.group("q")}{new_val}{m.group("q")}'

    return CLASS_ATTR.sub(repl, text), changed, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total_files = total_changes = 0
    unknowns: dict[str, int] = {}
    skipped_logic_files = 0

    for p in sorted(TEMPLATES.rglob("*.html")):
        rel = p.relative_to(REPO).as_posix()
        if rel in EXCLUDE_FILES or any(part in rel for part in EXCLUDE_DIR_PARTS):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if "badge" not in src:
            continue
        new, changed, notes = process(src)
        for n in notes:
            unknowns[n] = unknowns.get(n, 0) + 1
        if changed:
            total_files += 1
            total_changes += changed
            if args.apply and new != src:
                p.write_text(new, encoding="utf-8")
            elif not args.apply:
                print(f"  {rel}: {changed} badge(s)")

    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {total_changes} badges in {total_files} files")
    if unknowns:
        print("Unrecognised colours left untouched (manual review):")
        for k, v in sorted(unknowns.items(), key=lambda kv: -kv[1]):
            print(f"  {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
