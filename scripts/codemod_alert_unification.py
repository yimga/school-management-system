#!/usr/bin/env python3
"""Wave D codemod: fold static Bootstrap alerts onto the .rmc-banner grammar.

Rewrites `class="..."` attributes that use a static `alert alert-X` flavour into
`rmc-banner` + a semantic tone. Other utility classes (spacing, borders, flex,
small, etc.) are preserved.

SAFETY (mirrors the badge codemod):
  * Only touches a class attribute with a standalone `alert` token AND a known
    `alert-X` colour AND no `rmc-banner` already.
  * SKIPS `alert-dismissible` (keeps Bootstrap's `.alert` + `data-bs-dismiss` JS),
    any class attr with template logic (`{%`/`{{` — Django `alert-{{ tags }}`),
    and email/marketing/shell templates.
  * `alert-link` / `alert-heading` are child classes (no standalone `alert`
    token) so they are never matched — they keep working as-is.

Usage:
  python scripts/codemod_alert_unification.py            # dry-run + report
  python scripts/codemod_alert_unification.py --apply
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

TONE_SIGNALS = [
    ("error",   {"alert-danger"}),
    ("warning", {"alert-warning"}),
    ("success", {"alert-success"}),
    ("info",    {"alert-info"}),
    ("brand",   {"alert-primary"}),
    ("neutral", {"alert-secondary", "alert-light", "alert-dark"}),
]
ALL_SIGNALS = {t for _, s in TONE_SIGNALS for t in s}
MOD = {
    "error": "rmc-banner--error",
    "warning": "rmc-banner--warning",
    "success": "rmc-banner--success",
    "info": "rmc-banner--info",
    "brand": "rmc-banner--brand",
    "neutral": "",  # base .rmc-banner is neutral
}

CLASS_ATTR = re.compile(r"""class=(?P<q>["'])(?P<val>.*?)(?P=q)""", re.DOTALL)


def transform_class(val: str) -> tuple[str | None, str]:
    if "{%" in val or "{{" in val:
        return None, "skip-template-logic"
    tokens = val.split()
    if "alert" not in tokens:
        return None, "skip-not-alert"
    if any(t == "rmc-banner" or t.startswith("rmc-banner--") for t in tokens):
        return None, "skip-already"
    if "alert-dismissible" in tokens:
        return None, "skip-dismissible"

    present = set(tokens)
    tone = None
    for name, sig in TONE_SIGNALS:
        if present & sig:
            tone = name
            break
    # an unknown alert-* colour → don't guess
    unknown = [t for t in tokens if t.startswith("alert-") and t not in ALL_SIGNALS
               and t not in ("alert-link", "alert-heading")]
    if tone is None and unknown:
        return None, "skip-unknown:" + ",".join(unknown)
    if tone is None:
        tone = "neutral"

    out = ["rmc-banner"]
    if MOD[tone]:
        out.append(MOD[tone])
    for t in tokens:
        if t == "alert" or t in ALL_SIGNALS:
            continue
        out.append(t)
    return " ".join(out), "rewrite:" + tone


def process(text: str) -> tuple[str, int, dict[str, int]]:
    changed = 0
    notes: dict[str, int] = {}

    def repl(m: re.Match) -> str:
        nonlocal changed
        new_val, status = transform_class(m.group("val"))
        if status.startswith("skip-unknown") or status == "skip-dismissible":
            notes[status] = notes.get(status, 0) + 1
        if new_val is None:
            return m.group(0)
        changed += 1
        return f'class={m.group("q")}{new_val}{m.group("q")}'

    return CLASS_ATTR.sub(repl, text), changed, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total_files = total = 0
    agg: dict[str, int] = {}
    for p in sorted(TEMPLATES.rglob("*.html")):
        rel = p.relative_to(REPO).as_posix()
        if rel in EXCLUDE_FILES or any(part in rel for part in EXCLUDE_DIR_PARTS):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if "alert" not in src:
            continue
        new, changed, notes = process(src)
        for k, v in notes.items():
            agg[k] = agg.get(k, 0) + v
        if changed:
            total_files += 1
            total += changed
            if args.apply and new != src:
                p.write_text(new, encoding="utf-8")
            elif not args.apply:
                print(f"  {rel}: {changed}")

    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {total} alerts in {total_files} files")
    if agg:
        print("Intentionally skipped:")
        for k, v in sorted(agg.items(), key=lambda kv: -kv[1]):
            print(f"  {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
