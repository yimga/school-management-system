"""Consistency codemod: bring operational data tables onto `.rmc-data-table`.

OMNI consistency wave (2026-06-02). The platform's canonical premium table
grammar is `.rmc-data-table` (rmc-data-table.css). An audit found only ~44%
of tables carry it; the rest render raw Bootstrap, so the SAME list looks
premium on one surface and plain on another.

This codemod adds the additive, CSS-only `rmc-data-table` class to every
`<table>` that ALREADY carries `table-family` (the operational-data-table
marker) but lacks `rmc-data-table`. It deliberately does NOT touch:
  * tables without `table-family` (bare/layout/print tables — judgment needed),
  * anything under templates/reports/ (PDF/export print domain with bespoke
    cameroon-* / cam classes — rmc-data-table would fight the print layout).

The class is purely visual; row-detail/bulk behaviours come from separate
`data-rmc-*` attributes, so adding the class alone cannot change behaviour.

Usage:
    python scripts/codemod_rmc_data_table_consistency.py            # dry-run
    python scripts/codemod_rmc_data_table_consistency.py --apply    # write
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
EXCLUDE_DIRS = {"reports"}  # print/PDF domain — bespoke table classes

# Match an opening <table ...> tag and capture its class="..." value.
_TABLE_TAG = re.compile(r"<table\b[^>]*\bclass=\"([^\"]*)\"", re.IGNORECASE)


def _should_skip(path: Path) -> bool:
    rel = path.relative_to(TEMPLATES)
    return len(rel.parts) > 0 and rel.parts[0] in EXCLUDE_DIRS


def process(text: str) -> tuple[str, int]:
    changes = 0

    def repl(m: re.Match) -> str:
        nonlocal changes
        whole = m.group(0)
        classes = m.group(1)
        tokens = classes.split()
        if "table-family" not in tokens:
            return whole  # not an operational data table — leave alone
        if "rmc-data-table" in tokens:
            return whole  # already consistent
        changes += 1
        new_classes = classes + " rmc-data-table"
        return whole.replace(f'class="{classes}"', f'class="{new_classes}"', 1)

    new_text = _TABLE_TAG.sub(repl, text)
    return new_text, changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()

    total_files = 0
    total_changes = 0
    touched: list[tuple[str, int]] = []

    for path in sorted(TEMPLATES.rglob("*.html")):
        if _should_skip(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new_text, changes = process(text)
        if changes:
            total_files += 1
            total_changes += changes
            touched.append((str(path.relative_to(TEMPLATES)), changes))
            if args.apply:
                path.write_text(new_text, encoding="utf-8")

    for rel, n in touched:
        print(f"  {'PATCH' if args.apply else 'WOULD-PATCH'} {rel} (+{n})")
    print(
        f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: "
        f"{total_changes} table(s) across {total_files} file(s) "
        f"{'updated' if args.apply else 'would be updated'}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
