#!/usr/bin/env python3
"""Zero-tolerance gate: every <th> must declare a header association.

A `<th>` with no `scope=` (or explicit `headers=`) leaves screen readers to guess
whether the cell heads its column or its row — ambiguous in any table that isn't
a trivial single-header-row grid (WCAG 1.3.1 Info and Relationships). This scanner
flags `<th>` tags missing both `scope=` and `headers=` across templates/.

`<thead>` is NOT matched (the `\\b` after `th` excludes it).

Mark an intentional exception with `<!-- th-scope-allow: <reason> -->` on the
tag's line or the line directly above it.

Usage:
  python scripts/scan_th_scope.py             # report + exit 1 if over baseline
  python scripts/scan_th_scope.py --json      # machine-readable
  python scripts/scan_th_scope.py --update-baseline
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"
BASELINE = REPO / "var" / "security-audit-baseline-th-scope.json"
ALLOW = "th-scope-allow"

# A <th ...> opening tag carrying neither scope= nor headers=. `<th\b` excludes
# `<thead>` (no word boundary between "th" and "ead").
TH_NO_SCOPE = re.compile(
    r"<th\b"
    r"(?![^>]*\bscope=)"
    r"(?![^>]*\bheaders=)"
    r"[^>]*>",
    re.IGNORECASE,
)


def scan_text(text: str) -> list[int]:
    lines = text.splitlines()
    out: list[int] = []
    for m in TH_NO_SCOPE.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        ctx = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if line_no >= 2:
            ctx += " " + lines[line_no - 2]
        if ALLOW in ctx:
            continue
        out.append(line_no)
    return out


def collect() -> list[str]:
    findings: list[str] = []
    for p in sorted(TEMPLATES.rglob("*.html")):
        for ln in scan_text(p.read_text(encoding="utf-8", errors="replace")):
            findings.append(f"{p.relative_to(REPO).as_posix()}:{ln}")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()

    findings = collect()
    count = len(findings)

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"finding_count": count, "findings": findings}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"baseline updated: finding_count={count}")
        return 0

    if args.json:
        print(json.dumps({"finding_count": count, "findings": findings}, indent=2))
        return 0

    print(f"<th> tags missing scope=/headers=: {count}")
    for f in findings[:60]:
        print(f"  {f}")

    baseline = 0
    if BASELINE.exists():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0)
    if count > baseline:
        print(f"FAIL: {count} > baseline {baseline} — add scope=\"col\"/\"row\" (or "
              f"headers=) or a <!-- {ALLOW}: reason --> marker.")
        return 1
    print(f"OK (baseline {baseline})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
