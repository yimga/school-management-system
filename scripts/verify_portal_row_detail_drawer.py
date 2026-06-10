#!/usr/bin/env python3
"""Verify portal row-detail drawer dismiss + shell wiring contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

JS = REPO / "static" / "js" / "rmc-portal-row-detail-drawer.js"
PROVISION_JS = REPO / "static" / "js" / "rmc-copilot-lens-provision.js"
CSS = REPO / "static" / "css" / "rmc-portal-row-detail-drawer.css"
DRAWER = REPO / "templates" / "partials" / "portal_row_detail_drawer.html"
SHELL = REPO / "templates" / "control_plane_skeleton.html"
PORTAL = REPO / "templates" / "portal_base.html"
SCHOOLS_DIR = REPO / "templates" / "schools"

OPERATOR_LENS_PAGES = [
    (
        REPO / "templates" / "schools" / "super_schools_list.html",
        "data-rmc-row-lens-api",
        "data-rmc-row-requeue-api",
    ),
    (
        REPO / "templates" / "schools" / "super_operator_team_roster.html",
        "data-rmc-row-lens-api",
        None,
    ),
    (
        REPO / "templates" / "schools" / "super_offboarding_queue.html",
        "data-rmc-row-lens-api",
        "data-rmc-row-requeue-api",
    ),
    (
        REPO / "templates" / "schools" / "super_tenant_health.html",
        "data-rmc-row-lens-api",
        "data-rmc-row-requeue-api",
    ),
    (
        REPO / "templates" / "schools" / "super_dashboard.html",
        "data-rmc-row-lens-api",
        "data-rmc-row-requeue-api",
    ),
]

REQUIRED_JS = [
    "window.rmcRowDetailDismiss",
    "rmcPortalRowDetailDrawerLoaded",
    "data-rmc-portal-row-detail-dismiss",
    "hidden.bs.offcanvas",
    "rmc:row-detail-close",
    "dedupeDrawerDom",
    "renderHealthChips",
    "usesControlPlaneCopilotLens",
    "lensApiUrl",
]

REQUIRED_DRAWER = [
    'id="rmcPortalRowDetailDrawer"',
    "data-rmc-portal-row-detail-dismiss",
    "data-rmc-portal-row-detail-avatar",
    "rmcPortalRowDetailKbdHint",
]

REQUIRED_CSS = [
    ".rmc-portal-row-detail-drawer",
    ".rmc-row-detail-drawer__avatar",
    "z-index:",
]

BUNDLE_PATTERN = re.compile(r'include\s+"partials/portal_row_detail_drawer_bundle.html"')
EXTENDS_CP_BASE = re.compile(r'extends\s+"control_plane_base\.html"')
LENS_ROW_PARTIAL = "rmc_school_lens_api_attrs.html"
LENS_API_PARTIAL = "rmc_school_lens_api_attrs.html"


def _page_has_explicit_row_detail(text: str) -> bool:
    return 'data-rmc-row-detail="1"' in text or LENS_ROW_PARTIAL in text


def _page_has_lens_api_attr(text: str, attr: str) -> bool:
    return attr in text or LENS_ROW_PARTIAL in text or LENS_API_PARTIAL in text


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    js_text = JS.read_text(encoding="utf-8", errors="replace")
    for needle in REQUIRED_JS:
        if needle not in js_text:
            _fail(f"rmc-portal-row-detail-drawer.js missing {needle!r}")

    if not PROVISION_JS.is_file():
        _fail("rmc-copilot-lens-provision.js missing")
    provision_text = PROVISION_JS.read_text(encoding="utf-8", errors="replace")
    if "rmc:row-detail-open" not in provision_text:
        _fail("rmc-copilot-lens-provision.js must listen for rmc:row-detail-open")

    drawer_text = DRAWER.read_text(encoding="utf-8", errors="replace")
    for needle in REQUIRED_DRAWER:
        if needle not in drawer_text:
            _fail(f"portal_row_detail_drawer.html missing {needle!r}")

    css_text = CSS.read_text(encoding="utf-8", errors="replace")
    for needle in REQUIRED_CSS:
        if needle not in css_text:
            _fail(f"rmc-portal-row-detail-drawer.css missing {needle!r}")

    shell_text = SHELL.read_text(encoding="utf-8", errors="replace")
    if "portal_row_detail_drawer_bundle.html" not in shell_text:
        _fail("control_plane_skeleton.html must include portal_row_detail_drawer_bundle.html")
    if "rmc-copilot-lens-provision.js" not in shell_text:
        _fail("control_plane_skeleton.html must load rmc-copilot-lens-provision.js")

    portal_text = PORTAL.read_text(encoding="utf-8", errors="replace")
    if "portal_row_detail_drawer_bundle.html" not in portal_text:
        _fail("portal_base.html must include portal_row_detail_drawer_bundle.html")

    for page, lens_attr, requeue_attr in OPERATOR_LENS_PAGES:
        text = page.read_text(encoding="utf-8", errors="replace")
        if BUNDLE_PATTERN.search(text):
            _fail(f"{page.name} must not duplicate drawer bundle (shell provides it)")
        if 'data-rmc-row-detail-table="1"' not in text and "data-rmc-row-detail-cards" not in text:
            _fail(f"{page.name} missing row detail table or card surface")
        if not _page_has_explicit_row_detail(text):
            _fail(f"{page.name} missing explicit row detail rows")
        if not _page_has_lens_api_attr(text, lens_attr):
            _fail(f"{page.name} missing {lens_attr} on rows")
        if requeue_attr and not _page_has_lens_api_attr(text, requeue_attr):
            _fail(f"{page.name} missing {requeue_attr} on school rows")
        if "data-rmc-copilot-page-lens" not in text:
            _fail(f"{page.name} missing data-rmc-copilot-page-lens playbook key")

    duplicate_cp_pages: list[str] = []
    for path in sorted(SCHOOLS_DIR.glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not EXTENDS_CP_BASE.search(text):
            continue
        if BUNDLE_PATTERN.search(text):
            duplicate_cp_pages.append(path.name)
    if duplicate_cp_pages:
        sample = ", ".join(duplicate_cp_pages[:8])
        extra = len(duplicate_cp_pages) - 8
        suffix = f" (+{extra} more)" if extra > 0 else ""
        _fail(
            "control_plane_base schools templates must not duplicate drawer bundle "
            f"(shell provides it): {sample}{suffix}"
        )

    print("PASS: portal row-detail drawer global contract clean")


if __name__ == "__main__":
    main()
