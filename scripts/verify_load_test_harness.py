#!/usr/bin/env python3
"""Verify OSS load-test harness artifacts exist (stdlib-only; no Locust install required).

CI gate: ensures ``scripts/load/locustfile_attendance_wal.py`` is present and
syntactically valid. Full 50k concurrent proof runs in staging with Locust or k6.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCUST_FILE = ROOT / "scripts" / "load" / "locustfile_attendance_wal.py"
K6_FILE = ROOT / "scripts" / "load" / "k6_attendance_smoke.js"
K6_NOTE = ROOT / "scripts" / "load" / "README.md"


def main() -> int:
    errors: list[str] = []
    if not LOCUST_FILE.is_file():
        errors.append(f"missing: {LOCUST_FILE.relative_to(ROOT)}")
    else:
        try:
            ast.parse(LOCUST_FILE.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append(f"syntax error in locustfile: {exc}")
        text = LOCUST_FILE.read_text(encoding="utf-8")
        if "AttendanceWalUser" not in text:
            errors.append("locustfile missing AttendanceWalUser class")
    if not K6_FILE.is_file():
        errors.append(f"missing: {K6_FILE.relative_to(ROOT)}")
    else:
        k6_text = K6_FILE.read_text(encoding="utf-8")
        if "attendance" not in k6_text.lower():
            errors.append("k6 smoke script missing attendance scenario marker")
    if not K6_NOTE.is_file():
        errors.append(f"missing: {K6_NOTE.relative_to(ROOT)}")
    if errors:
        for err in errors:
            print(f"LOAD_HARNESS_FAIL: {err}", file=sys.stderr)
        return 1
    print("LOAD_HARNESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
