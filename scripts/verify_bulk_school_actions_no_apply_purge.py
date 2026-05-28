#!/usr/bin/env python3
"""Verifier: permanent purge (apply_purge) must not ship on bulk schools list or API.

Production safety: irreversible tenant delete stays on Tenant 360 with per-slug
confirmation — never on multi-select bulk bar.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

FORBIDDEN_BULK_ACTIONS = frozenset(
    {
        "apply_purge",
        "purge",
        "purge_apply",
        "permanent_purge",
        "run_apply_purge",
    }
)


def _text(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _allowed_actions_from_bulk_module() -> set[str]:
    path = REPO / "apps" / "schools" / "bulk_operator_actions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "ALLOWED_SCHOOL_ACTIONS"):
                continue
            call = node.value
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "frozenset"
                and len(call.args) == 1
                and isinstance(call.args[0], ast.Set)
            ):
                continue
            return {
                elt.value
                for elt in call.args[0].elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
    return set()


def _bulk_actions_from_schools_list_template() -> list[dict]:
    raw = _text("templates/schools/super_schools_list.html")
    m = re.search(r"data-rmc-bulk-actions='(\[.*?\])'", raw, re.DOTALL)
    if not m:
        return []
    # Template uses escapejs inside JSON strings — strip Django tags for action scan.
    blob = m.group(1)
    blob = re.sub(r"\{\%[^%]+%\}", "", blob)
    blob = re.sub(r"\{\{[^}]+\}\}", '""', blob)
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def main() -> int:
    findings: list[str] = []

    allowed = _allowed_actions_from_bulk_module()
    if not allowed:
        findings.append("ALLOWED_SCHOOL_ACTIONS missing or unreadable in bulk_operator_actions.py")
    else:
        blocked = allowed & FORBIDDEN_BULK_ACTIONS
        if blocked:
            findings.append(f"ALLOWED_SCHOOL_ACTIONS must not include: {sorted(blocked)}")
        if "apply_purge" in allowed:
            findings.append("apply_purge must not be in ALLOWED_SCHOOL_ACTIONS")

    bulk_py = _text("apps/schools/bulk_operator_actions.py")
    if re.search(r"\bapply_purge\s*\(", bulk_py):
        findings.append("bulk_operator_actions.py must not call apply_purge()")
    if re.search(r"from\s+apps\.schools\.tenant_offboarding\s+import\s+.*apply_purge", bulk_py):
        findings.append("bulk_operator_actions.py must not import apply_purge")

    list_actions = _bulk_actions_from_schools_list_template()
    for entry in list_actions:
        action = str(entry.get("action") or entry.get("id") or "")
        if action in FORBIDDEN_BULK_ACTIONS or "apply_purge" in action.lower():
            findings.append(f"super_schools_list bulk action forbidden: {action!r}")

    list_html = _text("templates/schools/super_schools_list.html")
    if '"action":"apply_purge"' in list_html.replace(" ", "") or '"action": "apply_purge"' in list_html:
        findings.append('super_schools_list.html wires action "apply_purge"')
    if re.search(r'"action"\s*:\s*"purge"', list_html) and "purge_dry_run" not in list_html:
        findings.append('super_schools_list.html may wire bare "purge" action (not purge_dry_run)')

    tenant_360 = _text("templates/schools/super_tenant_360.html")
    if "apply_purge" not in tenant_360 and "Permanent delete tenant" not in tenant_360:
        findings.append(
            "super_tenant_360 must retain per-tenant permanent delete (apply_purge path)"
        )

    if findings:
        print("BULK_SCHOOL_ACTIONS_NO_APPLY_PURGE_FAIL")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("BULK_SCHOOL_ACTIONS_NO_APPLY_PURGE_PASS")
    print(f"  allowed_actions={sorted(allowed)}")
    print(f"  list_post_actions={len([a for a in list_actions if a.get('kind') == 'post'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
