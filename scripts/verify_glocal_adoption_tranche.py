#!/usr/bin/env python3
"""Glocal adoption tranche — drawer + glocal_tags + canvas role homes (tranches 1–2)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DRAWER_TARGETS: tuple[tuple[str, str], ...] = (
    ("templates/teacher/marks_entry.html", "marks_entry"),
    ("templates/teacher/marks_list.html", "marks_list"),
    ("templates/teacher/attendance.html", "teacher_attendance"),
    ("templates/portal/roll_call_student.html", "roll_call_student"),
    ("templates/parent/finance.html", "parent_finance"),
    ("templates/parent/results.html", "parent_results"),
    ("templates/parent/attendance_discipline.html", "parent_attendance_discipline"),
    ("templates/teacher/pay_history.html", "teacher_pay_history"),
    ("templates/teacher/leave.html", "teacher_leave"),
    ("templates/parent/wallet.html", "parent_wallet"),
    ("templates/portal/cahier_list.html", "cahier_list"),
)

IAM_TARGETS: tuple[str, ...] = (
    "templates/teacher/dashboard.html",
    "templates/teacher/marks_list.html",
    "templates/teacher/attendance.html",
    "templates/parent/dashboard.html",
    "templates/parent/finance.html",
    "templates/parent/results.html",
    "templates/parent/attendance_discipline.html",
    "templates/teacher/pay_history.html",
    "templates/teacher/leave.html",
    "templates/parent/wallet.html",
    "templates/accounts/backend_dashboard.html",
    "templates/accounts/tenant_identity_roster.html",
)

CANVAS_ROLE_HOMES: tuple[tuple[str, str, str], ...] = (
    ("templates/teacher/dashboard.html", "canvas", "dashboard-page-teacher"),
    ("templates/parent/dashboard.html", "canvas", "dashboard-page-parent"),
)

ROLE_LITERAL = re.compile(
    r">\s*(Administrator|Headteacher|Teacher|Parent|Student)\s*<",
    re.IGNORECASE,
)


def _check_drawer_targets() -> list[str]:
    findings: list[str] = []
    for rel, label in DRAWER_TARGETS:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in (
            "portal_row_detail_drawer",
            "data-rmc-row-detail-table",
            "rmc-portal-row-detail-drawer.js",
        ):
            if needle not in text:
                findings.append(f"{label}: missing {needle}")
        if "data-rmc-row-detail-table" in text and "data-rmc-row-detail=" not in text:
            findings.append(f"{label}: table wired but no data-rmc-row-detail rows")
    return findings


def _check_iam_targets() -> list[str]:
    findings: list[str] = []
    vocab = ROOT / "apps/platform_runtime/glocal_vocabulary.py"
    tags = ROOT / "apps/platform_runtime/templatetags/glocal_tags.py"
    if not vocab.is_file() or not tags.is_file():
        findings.append("glocal vocabulary kernel missing")
    for rel in IAM_TARGETS:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "glocal_tags" not in text:
            findings.append(f"{rel}: missing glocal_tags load")
        if ROLE_LITERAL.search(text) and "glocal_token" not in text and "localized_role" not in text:
            findings.append(f"{rel}: hardcoded role label without glocal_token")
    return findings


def _check_canvas_role_homes() -> list[str]:
    findings: list[str] = []
    css = ROOT / "static/css/rmc-tenant-workspace-canvas.css"
    if not css.is_file():
        findings.append("missing rmc-tenant-workspace-canvas.css")
    for rel, policy, body_class in CANVAS_ROLE_HOMES:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "body_scroll_policy" not in text or policy not in text:
            findings.append(f"{rel}: missing body_scroll_policy {policy}")
        if body_class not in text:
            findings.append(f"{rel}: missing {body_class}")
        if "rmc-tenant-workspace-canvas.css" not in text:
            findings.append(f"{rel}: missing workspace canvas stylesheet")
    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    if "body_scroll_policy" not in portal:
        findings.append("portal_base missing body_scroll_policy block")
    return findings


def main() -> int:
    findings: list[str] = []
    findings.extend(_check_drawer_targets())
    findings.extend(_check_iam_targets())
    findings.extend(_check_canvas_role_homes())

    if findings:
        print("verify_glocal_adoption_tranche: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_glocal_adoption_tranche: GLOCAL_ADOPTION_TRANCHE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
