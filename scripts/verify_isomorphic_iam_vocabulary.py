#!/usr/bin/env python3
"""Batch 1531 — hot-path templates use glocal_token or localized role helpers."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = (
    "templates/teacher/dashboard.html",
    "templates/teacher/marks_list.html",
    "templates/teacher/attendance.html",
    "templates/parent/dashboard.html",
    "templates/parent/finance.html",
    "templates/parent/results.html",
    "templates/parent/attendance_discipline.html",
    "templates/accounts/backend_dashboard.html",
    "templates/accounts/tenant_identity_roster.html",
)

ROLE_LITERAL = re.compile(
    r">\s*(Administrator|Headteacher|Teacher|Parent|Student)\s*<",
    re.IGNORECASE,
)


def main() -> int:
    findings: list[str] = []

    vocab = ROOT / "apps/platform_runtime/glocal_vocabulary.py"
    tags = ROOT / "apps/platform_runtime/templatetags/glocal_tags.py"
    if not vocab.is_file() or not tags.is_file():
        findings.append("glocal vocabulary kernel missing")

    for rel in TARGETS:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "glocal_tags" not in text:
            findings.append(f"{rel}: missing glocal_tags load")
        if "glocal_token" not in text and "localized_role" not in text and "effective_role" not in text:
            if ROLE_LITERAL.search(text):
                findings.append(f"{rel}: hardcoded role label without glocal_token")

    if findings:
        print("verify_isomorphic_iam_vocabulary: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_isomorphic_iam_vocabulary: ISOMORPHIC_IAM_VOCABULARY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
