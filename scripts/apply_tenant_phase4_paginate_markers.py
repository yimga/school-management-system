#!/usr/bin/env python3
"""Add data-rmc-scroll-policy=paginate to tenant portal list templates (batch 1489)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    "templates/portal/cahier_list.html",
    "templates/portal/office_document_list.html",
    "templates/portal/signature_pending_list.html",
    "templates/portal/configure/lexicon_settings.html",
    "templates/accounts/messages.html",
    "templates/portal/faq_list.html",
    "templates/portal/kb_category.html",
    "templates/people/backend_student_list.html",
    "templates/finance/invoices.html",
    "templates/finance/payments.html",
    "templates/finance/dashboard.html",
    "templates/finance/invoice_detail.html",
    "templates/teacher/marks_entry.html",
    "templates/teacher/marks_list.html",
    "templates/portal/roll_call_teacher.html",
    "templates/parent/finance.html",
    "templates/parent/results.html",
    "templates/parent/contact_school.html",
    "templates/people/backend_teacher_list.html",
    "templates/people/backend_classroom_list.html",
    "templates/portal/offline_sync_queue.html",
    "templates/portal/offline_sync_conflicts.html",
    "templates/portal/kb_search.html",
    "templates/portal/document_library_manage.html",
    "templates/portal/forums_home.html",
    "templates/teacher/attendance.html",
    "templates/parent/attendance_discipline.html",
    "templates/portal/support_help_hub.html",
    "templates/finance/requests.html",
    "templates/people/backend_guardian_list.html",
    "templates/portal/signature_requests_manage.html",
    "templates/communication/group_list.html",
]


def _inject(body: str) -> str:
    if 'data-rmc-scroll-policy="paginate"' in body:
        return body
    anchor = "{% block content %}"
    idx = body.find(anchor)
    if idx < 0:
        return body
    rest = body[idx + len(anchor) :]
    match = re.search(r"<div(\s[^>]*)>", rest)
    if not match:
        return body
    full = match.group(0)
    if "data-rmc-scroll-policy" in full:
        return body
    attrs = match.group(1)
    replacement = (
        f"<div{attrs} data-rmc-scroll-policy=\"paginate\" "
        'data-page-archetype="task-list">'
    )
    return body[: idx + len(anchor)] + rest.replace(full, replacement, 1)


def main() -> int:
    changed = 0
    missing = 0
    for rel in TARGETS:
        path = ROOT / rel
        if not path.is_file():
            missing += 1
            print(f"skip missing {rel}", file=sys.stderr)
            continue
        original = path.read_text(encoding="utf-8")
        updated = _inject(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(f"updated {rel}")
    print(
        f"apply_tenant_phase4_paginate_markers: {changed} updated, "
        f"{missing} missing, {len(TARGETS)} targets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
