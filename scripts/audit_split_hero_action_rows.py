#!/usr/bin/env python3
"""Detect split cp-hero__actions rows (primary CTAs on one line, section nav on another)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

SPLIT_PATTERN = re.compile(
    r"</div>\s*<nav\s+class=\"cp-hero__actions",
    re.IGNORECASE,
)
LEGACY_SECTIONS_NAV = re.compile(
    r"cp-hero__actions--sections",
    re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    findings: list[dict[str, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT).as_posix()
        if SPLIT_PATTERN.search(text):
            findings.append(
                {
                    "file": rel,
                    "issue": "split_hero_action_rows",
                    "severity": "high",
                }
            )
        if LEGACY_SECTIONS_NAV.search(text) and "cp-hero__actions--toolbar" not in text:
            findings.append(
                {
                    "file": rel,
                    "issue": "legacy_sections_nav_without_unified_toolbar",
                    "severity": "medium",
                }
            )

    payload = {
        "finding_count": len(findings),
        "findings": findings,
    }
    out = ROOT / "docs/generated/split_hero_action_rows_audit.json"
    if args.write:
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    elif findings:
        print(f"audit_split_hero_action_rows: {len(findings)} finding(s)", file=sys.stderr)
        for f in findings:
            print(f"  [{f['severity']}] {f['file']}: {f['issue']}", file=sys.stderr)
        return 1

    print("audit_split_hero_action_rows: 0 findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
