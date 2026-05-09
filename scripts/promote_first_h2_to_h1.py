"""promote_first_h2_to_h1 — small targeted helper for the missing_h1 backlog.

For every template that:
  1. Extends a base (i.e. is a real page, not a partial), AND
  2. Has zero ``<h1>`` elements, AND
  3. Has at least one ``<h2>`` element,

…we promote ONLY the first ``<h2>`` to ``<h1>`` (and back to ``</h1>``).

Why this is safe in practice:
  - Pages that already have an h1 are skipped (no change).
  - Pages with only h3/h4 are skipped (the helper wouldn't know which header
    is the "page title" — operator must add an h1 manually).
  - The promotion is purely syntactic: <h2 -> <h1, </h2> -> </h1>. CSS that
    selects ``.page-title`` etc. on the element is unaffected.

Defaults to dry-run; pass --apply to actually write changes.

Usage::

    python scripts/promote_first_h2_to_h1.py            # dry-run
    python scripts/promote_first_h2_to_h1.py --apply    # write changes
    python scripts/promote_first_h2_to_h1.py --only finance,portal  # restrict
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"

RE_EXTENDS = re.compile(r'\{%\s*extends\s+["\']([^"\']+)["\']', re.IGNORECASE)
RE_H1 = re.compile(r"<h1[\s>]", re.IGNORECASE)
RE_H2_OPEN = re.compile(r"<h2(\s[^>]*)?>", re.IGNORECASE)
SKIP_DIR_PARTS = {"partials", "components", "errors", "emails", "admin", "unfold"}


def _is_partial(path: Path) -> bool:
    return any(p.lower() in SKIP_DIR_PARTS for p in path.parts)


def _candidate_files(only: set[str] | None) -> list[Path]:
    out: list[Path] = []
    for p in TEMPLATES_ROOT.rglob("*.html"):
        if _is_partial(p):
            continue
        if only:
            rel_parts = {x.lower() for x in p.relative_to(TEMPLATES_ROOT).parts}
            if not (rel_parts & only):
                continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not RE_EXTENDS.search(text):
            continue
        if RE_H1.search(text):
            continue
        if not RE_H2_OPEN.search(text):
            continue
        out.append(p)
    return out


def _promote(text: str) -> tuple[str, bool]:
    """Replace the first <h2 ...> with <h1 ...> and the matching </h2> with </h1>."""
    m = RE_H2_OPEN.search(text)
    if not m:
        return text, False
    start, end = m.start(), m.end()
    open_tag_attrs = m.group(1) or ""
    new_open = "<h1" + open_tag_attrs + ">"
    # Find the FIRST </h2> after the opening tag — naive but works for the
    # simple cases we care about (page-title h2 followed by its own close).
    close_idx = text.lower().find("</h2>", end)
    if close_idx == -1:
        return text, False
    new_text = (
        text[:start]
        + new_open
        + text[end:close_idx]
        + "</h1>"
        + text[close_idx + len("</h2>"):]
    )
    return new_text, True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run).")
    parser.add_argument("--only", type=str, default="", help="Comma-separated dir filter (e.g. finance,portal).")
    args = parser.parse_args()

    only = {p.strip().lower() for p in args.only.split(",") if p.strip()} or None
    candidates = _candidate_files(only)
    print(f"promote_first_h2_to_h1: {len(candidates)} candidate template(s)")

    promoted = 0
    skipped = 0
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        new_text, ok = _promote(text)
        if not ok:
            skipped += 1
            continue
        rel = path.relative_to(ROOT)
        if args.apply:
            path.write_text(new_text, encoding="utf-8")
            print(f"  PROMOTED {rel}")
        else:
            print(f"  WOULD PROMOTE {rel}")
        promoted += 1

    if not args.apply:
        print(f"\nDRY-RUN: would promote {promoted} file(s); {skipped} skipped (no matching </h2>).")
        print("Re-run with --apply to write.")
    else:
        print(f"\nDone. Promoted {promoted} file(s); {skipped} skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
