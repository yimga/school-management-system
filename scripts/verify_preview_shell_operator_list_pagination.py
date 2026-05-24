#!/usr/bin/env python3
"""Gate: high-traffic operator list views expose page_obj + pagination partial."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# view module path fragment -> template path
VIEW_TEMPLATE_PAIRS: tuple[tuple[str, str], ...] = (
    ("super_views_offboarding_queue.py", "templates/schools/super_offboarding_queue.html"),
    ("super_views_trust_surface.py", "templates/schools/super_platform_events.html"),
    ("super_views_catalog.py", "templates/schools/super_blueprints_catalog.html"),
    ("views_administration.py", "templates/platform_runtime/blueprint_marketplace.html"),
    ("views_administration.py", "templates/platform_runtime/pack_marketplace.html"),
    ("super_views_overview_surfaces.py", "templates/schools/super_schools_list.html"),
    ("super_views_config.py", "templates/schools/super_incidents_list.html"),
    ("views_administration.py", "templates/platform_runtime/change_requests.html"),
)


def _view_has_page_obj(view_rel: str) -> bool:
    path = ROOT / "apps" / view_rel.replace("/", "/").replace("schools/", "schools/")
    if view_rel.startswith("super_") or view_rel.startswith("views_"):
        if "schools" in view_rel or view_rel.startswith("super_"):
            candidates = list((ROOT / "apps" / "schools").glob(view_rel.split("/")[-1]))
            path = candidates[0] if candidates else ROOT / "apps" / "schools" / view_rel
        else:
            path = ROOT / "apps" / "platform_runtime" / view_rel
    if not path.is_file():
        # resolve by basename search
        name = Path(view_rel).name
        for base in (ROOT / "apps" / "schools", ROOT / "apps" / "platform_runtime"):
            hits = list(base.rglob(name))
            if hits:
                path = hits[0]
                break
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "page_obj":
            return True
        if isinstance(node, ast.Str) and node.s == "page_obj":  # noqa: UP036 py<3.12
            return True
    text = path.read_text(encoding="utf-8")
    return '"page_obj"' in text or "'page_obj'" in text


def main() -> int:
    findings: list[str] = []
    checks = (
        ("apps/schools/super_views_offboarding_queue.py", "templates/schools/super_offboarding_queue.html"),
        ("apps/schools/super_views_trust_surface.py", "templates/schools/super_platform_events.html"),
        ("apps/schools/super_views_catalog.py", "templates/schools/super_blueprints_catalog.html"),
        ("apps/platform_runtime/views_administration.py", "templates/platform_runtime/blueprint_marketplace.html"),
        ("apps/platform_runtime/views_administration.py", "templates/platform_runtime/pack_marketplace.html"),
        ("apps/schools/super_views_overview_surfaces.py", "templates/schools/super_schools_list.html"),
        ("apps/schools/super_views_config.py", "templates/schools/super_incidents_list.html"),
    )
    for view_rel, tpl_rel in checks:
        view_path = ROOT / view_rel
        tpl_path = ROOT / tpl_rel
        if not view_path.is_file():
            findings.append(f"missing view {view_rel}")
            continue
        body = view_path.read_text(encoding="utf-8")
        if not tpl_path.is_file():
            findings.append(f"missing template {tpl_rel}")
            continue
        tpl = tpl_path.read_text(encoding="utf-8")
        has_pager = (
            "components/pagination.html" in tpl
            or 'data-rmc-component="pagination"' in tpl
            or "rmc-pagination" in tpl
        )
        if not has_pager:
            findings.append(f"{tpl_rel}: missing numbered pagination markup")
        if tpl_rel.endswith("super_schools_list.html"):
            if '"page"' not in body and "'page'" not in body:
                findings.append(f"{view_rel}: schools list must pass page in context")
            continue
        if "page_obj" not in body:
            findings.append(f"{view_rel}: missing page_obj in render context")
    # change_requests already gated in phase4
    cr_tpl = ROOT / "templates/platform_runtime/change_requests.html"
    if cr_tpl.is_file() and "components/pagination.html" not in cr_tpl.read_text(encoding="utf-8"):
        findings.append("change_requests.html: missing pagination partial")

    if findings:
        print("verify_preview_shell_operator_list_pagination: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(
        "verify_preview_shell_operator_list_pagination: "
        "PREVIEW_SHELL_OPERATOR_LIST_PAGINATION_PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
