#!/usr/bin/env python3
"""Batch 1534 — QR / card-sweep attendance pilot gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []

    mod = ROOT / "apps/academics/qr_attendance.py"
    if not mod.is_file():
        findings.append("missing qr_attendance.py")
    else:
        text = mod.read_text(encoding="utf-8")
        for needle in ("apply_qr_sweep", "mint_student_attendance_token", "bulk_attendance"):
            if needle not in text:
                findings.append(f"qr_attendance missing {needle}")

    roll = ROOT / "templates/portal/roll_call_student.html"
    if not roll.is_file():
        findings.append("missing roll_call_student.html")
    else:
        body = roll.read_text(encoding="utf-8")
        if "qr-attendance" not in body and "qr_sweep" not in body:
            findings.append("roll_call_student missing QR sweep UI")

    views = (ROOT / "apps/portal/views_teacher.py").read_text(encoding="utf-8")
    if "apply_qr_sweep" not in views and "qr_sweep" not in views:
        findings.append("views_teacher missing QR sweep handler")

    tests = ROOT / "apps/academics/tests/test_qr_attendance.py"
    if not tests.is_file():
        findings.append("missing test_qr_attendance.py")

    if findings:
        print("verify_zero_input_attendance_pilot: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_zero_input_attendance_pilot: ZERO_INPUT_ATTENDANCE_PILOT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
