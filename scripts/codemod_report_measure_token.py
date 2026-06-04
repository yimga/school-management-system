"""LAY-2 codemod — single-source the operator-report reading measure.

Replaces hardcoded inline ``max-width: <N>rem`` caps with
``max-width: var(--rmc-report-measure)`` on the operator-report /
cp-evidence partials, so the report measure is tunable in ONE place
(``--rmc-report-measure`` in static/css/design-tokens.css).

ONLY touches lines that carry BOTH ``cp-evidence-page`` AND an inline
``max-width: <N>rem`` — i.e. the report-archetype container divs. Other
inline max-widths (auth forms, marketing, distinct surfaces) are left
alone. cwd-independent. Pass --apply to write; default is dry-run.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# Matches `max-width: 56rem` (optionally with decimals) on a cp-evidence line.
_MAXW = re.compile(r"max-width:\s*\d+(?:\.\d+)?rem")
_REPLACEMENT = "max-width: var(--rmc-report-measure)"


def process(text: str) -> tuple[str, int]:
    out_lines = []
    hits = 0
    for line in text.splitlines(keepends=True):
        if "cp-evidence-page" in line and _MAXW.search(line):
            new_line, n = _MAXW.subn(_REPLACEMENT, line)
            hits += n
            out_lines.append(new_line)
        else:
            out_lines.append(line)
    return "".join(out_lines), hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total_files = 0
    total_hits = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        if "cp-evidence-page" not in text:
            continue
        new_text, hits = process(text)
        if hits:
            total_files += 1
            total_hits += hits
            rel = path.relative_to(TEMPLATES.parent)
            print(f"{'APPLY' if args.apply else 'DRY'}  {rel}  ({hits})")
            if args.apply:
                path.write_text(new_text, encoding="utf-8")
    print(f"\n{total_hits} cap(s) across {total_files} file(s) "
          f"{'rewritten' if args.apply else 'would be rewritten'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
