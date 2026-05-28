#!/usr/bin/env python3
"""Batch 1533 — max 5 visible columns on .rmc-data-table (baseline 0)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "var/security-audit-baseline-table-column-budget.json"

TABLE_RE = re.compile(
    r'<table[^>]*class="[^"]*rmc-data-table[^"]*"[^>]*>(.*?)</table>',
    re.DOTALL | re.IGNORECASE,
)
TH_RE = re.compile(r"<th\b", re.IGNORECASE)
ALLOW_RE = re.compile(
    r"<!--\s*table-column-budget-allow:\s*[^>]+-->",
    re.IGNORECASE,
)

SCAN_FILES = (
    "templates/teacher/marks_entry.html",
    "templates/people/backend_student_list.html",
    "templates/people/backend_teacher_list.html",
    "templates/finance/invoices.html",
)


def scan_file(rel: str) -> list[str]:
    path = ROOT / rel
    if not path.is_file():
        return [f"missing {rel}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    if ALLOW_RE.search(text):
        return []
    findings: list[str] = []
    for match in TABLE_RE.finditer(text):
        th_count = len(TH_RE.findall(match.group(1)))
        if th_count > 5:
            findings.append(f"{rel}: {th_count} columns (max 5)")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings: list[str] = []
    for rel in SCAN_FILES:
        findings.extend(scan_file(rel))

    report = {
        "finding_count": len(findings),
        "findings": findings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.strict and BASELINE.is_file():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        if len(findings) > int(baseline.get("finding_count", 0)):
            print("scan_table_column_budget: FAIL baseline regression", file=sys.stderr)
            for f in findings:
                print(f"  - {f}", file=sys.stderr)
            return 1

    if findings and not args.update_baseline:
        print("scan_table_column_budget: FAIL", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"scan_table_column_budget: OK ({len(findings)} findings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
