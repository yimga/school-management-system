#!/usr/bin/env python3
"""Verify mutation views use canonical post-mutation navigation helpers."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IMPORT_MODULE = "services.post_delete_navigation"
HELPER_NAMES = frozenset(
    {
        "redirect_after_mutation",
        "redirect_after_delete",
        "redirect_after_save",
        "redirect_after_detail_mutation",
        "mutation_return_url",
        "resolve_return_url",
        "append_return_query",
        "safe_next_url",
        "finance_save_redirect",
        "finance_detail_redirect",
    }
)

VIEW_MODULES = {
    ROOT / "apps/schools/super_views_config_crud.py": {
        "redirect_after_delete",
        "redirect_after_save",
        "mutation_return_url",
    },
    ROOT / "apps/accounts/views_tenant_identity.py": HELPER_NAMES,
    ROOT / "apps/apicenter/views.py": {"redirect_after_delete"},
    ROOT / "apps/schools/super_views_operator_team.py": {
        "redirect_after_delete",
        "redirect_after_detail_mutation",
        "mutation_return_url",
    },
    ROOT / "apps/compliance/views_queue.py": {"redirect_after_save"},
    ROOT / "apps/people/views_backend.py": {"redirect_after_save", "mutation_return_url"},
    ROOT / "apps/schoolops/views_tenant_ops.py": {"redirect_after_save"},
    ROOT / "apps/schools/views_advancement.py": {
        "redirect_after_detail_mutation",
        "mutation_return_url",
    },
    ROOT / "apps/accounts/views.py": {"redirect_after_save", "mutation_return_url"},
    ROOT / "apps/finance/views_common.py": {
        "redirect_after_save",
        "redirect_after_detail_mutation",
    },
    ROOT / "apps/finance/views_invoicing.py": {
        "finance_save_redirect",
        "finance_detail_redirect",
    },
    ROOT / "apps/finance/views_access.py": {"finance_save_redirect", "redirect_after_save"},
    ROOT / "apps/finance/views_offline_bursar_queue.py": {"finance_save_redirect"},
    ROOT / "apps/finance/views_payments.py": {
        "finance_save_redirect",
        "finance_detail_redirect",
    },
    ROOT / "apps/finance/views_accounting.py": {"finance_save_redirect"},
    ROOT / "apps/finance/views_reports.py": {"finance_save_redirect"},
    ROOT / "apps/finance/views_requests.py": {"redirect_after_save"},
    ROOT / "apps/finance/views_marketplace_integration_credentials.py": {
        "redirect_after_save",
    },
    ROOT / "apps/portal/views_documents.py": {
        "redirect_after_delete",
        "redirect_after_save",
        "mutation_return_url",
    },
}

SAFE_NEXT_MIGRATIONS = (
    ROOT / "apps/siteconfig/views.py",
    ROOT / "apps/requests/views.py",
    ROOT / "apps/accounts/views_mfa.py",
    ROOT / "apps/api/oidc_rp.py",
)

TEMPLATE_MARKERS = (
    (ROOT / "templates/schools/super_crud_confirm_delete.html", 'name="next"'),
    (ROOT / "templates/schools/super_crud_form.html", 'name="next"'),
    (ROOT / "templates/accounts/tenant_identity_detail.html", 'name="next"'),
    (ROOT / "templates/accounts/rbac_dashboard.html", 'name="next"'),
    (ROOT / "templates/schools/super_operator_team_detail.html", 'name="next"'),
    (ROOT / "templates/people/backend_student_create.html", 'name="next"'),
    (ROOT / "templates/schools/advancement_donor_detail.html", 'name="next"'),
    (
        ROOT / "templates/portal/partials/document_library_manage_inner.html",
        'name="next"',
    ),
)


FINANCE_REDIRECT_HELPERS = frozenset({"finance_save_redirect", "finance_detail_redirect"})


def _imports_helper(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    finance_views = path.parent.name == "finance"
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = node.module or ""
        if mod == IMPORT_MODULE:
            for alias in node.names:
                found.add(alias.name)
        if finance_views and mod in {
            ".views_common",
            "views_common",
            "apps.finance.views_common",
        }:
            for alias in node.names:
                if alias.name in FINANCE_REDIRECT_HELPERS:
                    found.add(alias.name)
    return found


def _imports_safe_next(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "from services.post_delete_navigation import safe_next_url" in text:
        return True
    if "import safe_next_url as _safe_next_url" in text:
        return True
    return False


def main() -> int:
    failures: list[str] = []

    helper_path = ROOT / "services/post_delete_navigation.py"
    if not helper_path.is_file():
        failures.append(f"missing helper: {helper_path}")

    for path, required in VIEW_MODULES.items():
        if not path.is_file():
            failures.append(f"missing view module: {path}")
            continue
        found = _imports_helper(path)
        if not (found & required):
            names = ", ".join(sorted(required))
            failures.append(
                f"{path.relative_to(ROOT)} must import one of: {names}"
            )

    for path in SAFE_NEXT_MIGRATIONS:
        if not path.is_file():
            failures.append(f"missing safe_next migration target: {path}")
            continue
        if "def _safe_next_url" in path.read_text(encoding="utf-8"):
            failures.append(
                f"{path.relative_to(ROOT)} still defines local _safe_next_url"
            )
        if not _imports_safe_next(path):
            failures.append(
                f"{path.relative_to(ROOT)} must import safe_next_url from {IMPORT_MODULE}"
            )

    for path, marker in TEMPLATE_MARKERS:
        if not path.is_file():
            failures.append(f"missing template: {path}")
            continue
        if marker not in path.read_text(encoding="utf-8"):
            failures.append(f"{path.relative_to(ROOT)} missing hidden {marker}")

    if failures:
        print("verify_post_delete_navigation: FAIL", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("POST_DELETE_NAVIGATION_PASS")
    print("verify_post_delete_navigation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
