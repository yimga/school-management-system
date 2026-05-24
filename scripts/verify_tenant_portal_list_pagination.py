#!/usr/bin/env python3
"""Gate: tenant portal list views expose page_obj + pagination partial."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (view module, template, context key for page_obj in render)
TENANT_LIST_PAIRS: tuple[tuple[str, str], ...] = (
    ("apps/evals/views.py", "templates/teacher/marks_list.html"),
    ("apps/portal/views_parent_finance.py", "templates/parent/finance.html"),
    ("apps/finance/views_invoicing.py", "templates/finance/invoices.html"),
    ("apps/finance/views_payments.py", "templates/finance/payments.html"),
    ("apps/people/views_backend.py", "templates/people/backend_student_list.html"),
)


def main() -> int:
    findings: list[str] = []
    for view_rel, tpl_rel in TENANT_LIST_PAIRS:
        view_path = ROOT / view_rel
        tpl_path = ROOT / tpl_rel
        if not view_path.is_file():
            findings.append(f"missing {view_rel}")
            continue
        if not tpl_path.is_file():
            findings.append(f"missing {tpl_rel}")
            continue
        view_body = view_path.read_text(encoding="utf-8")
        tpl = tpl_path.read_text(encoding="utf-8")
        if '"page_obj"' not in view_body and "'page_obj'" not in view_body:
            findings.append(f"{view_rel}: missing page_obj in view context")
        has_pager = (
            "components/pagination.html" in tpl
            or 'data-rmc-component="pagination"' in tpl
            or "rmc-pagination" in tpl
        )
        if not has_pager:
            findings.append(f"{tpl_rel}: missing pagination partial")
        if 'data-rmc-scroll-policy="paginate"' not in tpl:
            findings.append(f"{tpl_rel}: missing data-rmc-scroll-policy=paginate")

    if findings:
        print("verify_tenant_portal_list_pagination: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_tenant_portal_list_pagination: TENANT_PORTAL_LIST_PAGINATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
