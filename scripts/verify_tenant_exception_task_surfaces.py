#!/usr/bin/env python3
"""Batch 1728 Wave B — P0 inner pages declare exception task surface markers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NEEDLES: list[tuple[str, str]] = [
    ("static/css/rmc-tenant-exception-task-surface.css", "rmc-tenant-exception-task"),
    ("templates/portal_base.html", "rmc-tenant-exception-task-surface.css"),
    ("templates/teacher/marks_list.html", "data-rmc-tenant-exception-task"),
    ("templates/teacher/marks_list.html", "data-rmc-filter-rail"),
    ("templates/people/backend_student_list.html", "data-rmc-tenant-exception-task"),
    ("templates/parent/finance.html", "data-rmc-tenant-exception-task"),
    ("templates/accounts/rbac_dashboard.html", "data-rmc-tenant-exception-task"),
]


def main() -> int:
    failures: list[str] = []
    for rel, needle in NEEDLES:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing file: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"{rel}: missing needle {needle!r}")
    if failures:
        print("verify_tenant_exception_task_surfaces: FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("verify_tenant_exception_task_surfaces: TENANT_EXCEPTION_TASK_SURFACES_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
