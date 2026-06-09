#!/usr/bin/env python3
"""Ensure only approved modules assign ``School.is_active`` for provisioning lifecycle."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-single-lifecycle-writer.json"

ALLOWED_SCHOOL_IS_ACTIVE_WRITERS = frozenset(
    {
        "apps/schools/tasks.py",
        "apps/schools/control_plane_lifecycle.py",
        "apps/schools/tenant_offboarding.py",
        "apps/schools/signup_views.py",
        "apps/lifecycle/services_offboarding.py",
    }
)

ALLOWED_COMPLETED_EVENT_WRITERS = frozenset(
    {
        "apps/schools/tasks.py",
        "apps/schools/control_plane_lifecycle.py",
        "apps/schools/tenant_offboarding.py",
        "apps/schools/signup_views.py",
    }
)

_SCHOOL_IS_ACTIVE_RE = re.compile(
    r"\bschool\.is_active\s*=",
    re.MULTILINE,
)
_COMPLETED_EVENT_RE = re.compile(
    r"SchoolProvisioningEvent\.(log_event|objects\.create)[\s\S]{0,200}?event_type\s*=\s*[\"']COMPLETED[\"']",
    re.MULTILINE,
)


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _scan_file(path: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    rel = _rel(path)
    if not rel.startswith("apps/"):
        return findings
    if (
        "/migrations/" in rel
        or "/tests" in rel
        or rel.endswith("_tests.py")
        or "/management/commands/" in rel
    ):
        return findings
    if rel in ALLOWED_SCHOOL_IS_ACTIVE_WRITERS and rel in ALLOWED_COMPLETED_EVENT_WRITERS:
        return findings

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return findings

    for match in _SCHOOL_IS_ACTIVE_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        if rel not in ALLOWED_SCHOOL_IS_ACTIVE_WRITERS:
            findings.append(
                {
                    "kind": "school_is_active_write",
                    "path": rel,
                    "line": str(line),
                }
            )

    for match in _COMPLETED_EVENT_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        if rel not in ALLOWED_COMPLETED_EVENT_WRITERS:
            findings.append(
                {
                    "kind": "completed_event_write",
                    "path": rel,
                    "line": str(line),
                }
            )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    findings: list[dict[str, str]] = []
    for path in sorted((REPO_ROOT / "apps").rglob("*.py")):
        findings.extend(_scan_file(path))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "findings": findings,
    }
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline {BASELINE} ({len(findings)} findings)")
        return 0

    if BASELINE.is_file():
        allowed = int(json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0))
    else:
        allowed = 0

    if args.strict and len(findings) > allowed:
        for row in findings[:40]:
            print(f"SINGLE_LIFECYCLE_WRITER_FAIL {row['kind']} {row['path']}:{row['line']}")
        if len(findings) > 40:
            print(f"... and {len(findings) - 40} more")
        print(f"SINGLE_LIFECYCLE_WRITER_FAIL count={len(findings)} baseline={allowed}")
        return 1

    print("SINGLE_LIFECYCLE_WRITER_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
