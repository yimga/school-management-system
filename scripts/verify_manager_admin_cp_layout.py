#!/usr/bin/env python3
"""Manager /admin/* layout gate: CSS scoping + HTML smoke (blank-main regression)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

CSS_FILES = (
    "static/css/admin-sidebar-scroll.css",
    "static/css/admin-base-site-shell.css",
    "static/css/admin-cp-parity.css",
    "static/css/rmc-sidebar-rail-contract.css",
    "static/css/rmc-shell-scroll-contract.css",
)

# Tenant-only row layout must not apply to unified manager admin page.
ROW_LAYOUT_OK = re.compile(
    r"#page:not\(\.admin-cp-unified-page\)\s*\{[^}]*flex-direction:\s*row",
    re.DOTALL,
)
FIRST_CHILD_TRAP = re.compile(
    r"#page:not\(\.admin-cp-unified-page\)(?::not\(:has\(\.admin-cp-unified-page\)\))?\s*>\s*div:first-child",
)
UNIFIED_COLUMN = re.compile(
    r"\.admin-cp-unified-page\s*\{[^}]*flex-direction:\s*column",
    re.DOTALL,
)
DOCUMENT_SCROLL_CONTRACT = re.compile(
    r"body\.admin-manager-shell\[data-rmc-cp-scroll=\"document\"\].*\.admin-cp-unified-page\s*\{[^}]*overflow:\s*visible",
    re.DOTALL,
)
DOCUMENT_MAIN_CONTRACT = re.compile(
    r"body\.admin-manager-shell\[data-rmc-cp-scroll=\"document\"\].*#cp-main-content\s*\{[^}]*overflow-y:\s*visible",
    re.DOTALL,
)
CANVAS_SCROLL_CONTRACT = re.compile(
    r"body\.admin-manager-shell\[data-rmc-cp-scroll=\"canvas\"\].*\.rmc-app-shell__canvas\s*\{[^}]*overflow-y:\s*auto",
    re.DOTALL,
)
SCROLL_CONTRACT_FILE = re.compile(
    r"rmc-shell-scroll-contract\.css",
    re.DOTALL,
)
AUTH_DOCUMENT_SCROLL = re.compile(
    r'data-rmc-cp-scroll="\{% block cp_scroll_mode %\}canvas\{% endblock %\}"',
    re.DOTALL,
)
AUTH_LANDING_ATTR = re.compile(
    r'data-rmc-auth-landing="1"',
    re.DOTALL,
)
PAGE_HAS_GUARD = re.compile(
    r"#page:not\(\.admin-cp-unified-page\):not\(:has\(\.admin-cp-unified-page\)\)",
    re.DOTALL,
)
CP_PAGE_BODY_CONTRACT = re.compile(
    r"cp-admin-page-body",
    re.DOTALL,
)


def check_css() -> list[str]:
    errors: list[str] = []
    for rel in CSS_FILES:
        path = REPO_ROOT / rel
        if not path.is_file():
            errors.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if rel.endswith("admin-sidebar-scroll.css"):
            if "#page {" in text and "admin-cp-unified-page" not in text.split("#page {")[0]:
                if re.search(r"^#page\s*\{", text, re.MULTILINE):
                    errors.append(
                        f"{rel}: unscoped #page row layout would break manager admin"
                    )
            if not FIRST_CHILD_TRAP.search(text):
                errors.append(
                    f"{rel}: missing #page:not(.admin-cp-unified-page) > div:first-child guard"
                )
        if rel.endswith("admin-cp-parity.css"):
            if not UNIFIED_COLUMN.search(text):
                errors.append(f"{rel}: missing column flex contract for .admin-cp-unified-page")
            if not DOCUMENT_SCROLL_CONTRACT.search(text):
                errors.append(
                    f"{rel}: missing document-scroll .admin-cp-unified-page overflow:visible contract"
                )
            if not DOCUMENT_MAIN_CONTRACT.search(text):
                errors.append(
                    f"{rel}: missing document-scroll #cp-main-content overflow-y:visible contract"
                )
            if not CANVAS_SCROLL_CONTRACT.search(text):
                errors.append(
                    f"{rel}: missing canvas-scroll .rmc-app-shell__canvas overflow-y:auto contract"
                )
        if rel.endswith("rmc-shell-scroll-contract.css"):
            if "overflow-y: auto !important" not in text:
                errors.append(f"{rel}: missing canvas overflow-y:auto repair")
            if "#page:has(.admin-cp-unified-page)" not in text:
                errors.append(f"{rel}: missing #page:has(.admin-cp-unified-page) unwind")
        if rel.endswith("admin-sidebar-scroll.css"):
            if not PAGE_HAS_GUARD.search(text):
                errors.append(
                    f"{rel}: missing :has(.admin-cp-unified-page) guard on legacy #page trap"
                )
    admin_base = (REPO_ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
    if "admin-cp-unified-page" not in admin_base:
        errors.append("templates/admin/base.html missing admin-cp-unified-page class")
    if "data-rmc-admin-cp-unified" not in admin_base:
        errors.append("templates/admin/base.html missing data-rmc-admin-cp-unified marker")
    if "cp-admin-page-body" not in admin_base:
        errors.append("templates/admin/base.html missing cp-admin-page-body (super parity)")
    if 'data-rmc-cp-scroll="main"' in admin_base:
        errors.append("templates/admin/base.html must not set data-rmc-cp-scroll=main on #page")
    if "rmc-app-shell admin-cp-unified-page" not in admin_base:
        errors.append("templates/admin/base.html must combine rmc-app-shell + admin-cp-unified-page")
    base_site = (REPO_ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
    if "data-rmc-cp-scroll', 'canvas'" not in base_site:
        errors.append(
            "templates/admin/base_site.html must set data-rmc-cp-scroll=canvas for manager admin"
        )
    if "rmc-app-shell.css" not in base_site:
        errors.append("templates/admin/base_site.html must load rmc-app-shell.css on manager host")
    chrome_styles = (REPO_ROOT / "templates/partials/rmc_platform_chrome_styles.html").read_text(
        encoding="utf-8"
    )
    if "rmc-shell-scroll-contract.css" not in chrome_styles:
        errors.append(
            "templates/partials/rmc_platform_chrome_styles.html must load rmc-shell-scroll-contract.css"
        )
    admin_login = (REPO_ROOT / "templates/auth/admin_login.html").read_text(encoding="utf-8")
    if '{% block cp_scroll_mode %}document{% endblock %}' not in admin_login:
        errors.append("templates/auth/admin_login.html must set cp_scroll_mode=document")
    if 'data-rmc-auth-landing="1"' not in admin_login:
        errors.append("templates/auth/admin_login.html must mark data-rmc-auth-landing=1")
    cp_sk = (REPO_ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    if '{% block cp_scroll_mode %}canvas{% endblock %}' not in cp_sk:
        errors.append("templates/control_plane_skeleton.html must expose cp_scroll_mode block")
    if "legacyPage.classList.add('admin-cp-unified-page')" not in base_site:
        errors.append(
            "templates/admin/base_site.html must tag legacy #page with admin-cp-unified-page"
        )
    if "control-plane-skeleton-root.css" not in base_site:
        errors.append("templates/admin/base_site.html must load control-plane-skeleton-root.css")
    if "manager-cockpit-v7.css" not in base_site:
        errors.append("templates/admin/base_site.html must load manager-cockpit-v7.css on manager host")
    if "rmc-cp-header-200x.css" not in base_site:
        errors.append("templates/admin/base_site.html must load rmc-cp-header-200x.css on manager host")
    if 'data-rmc-cp-header-200x="1"' not in admin_base:
        errors.append("templates/admin/base.html must use cp-header 200x stack on manager host")
    if "_activity_ticker.html" not in admin_base:
        errors.append("templates/admin/base.html must include live activity ticker in manager header")
    if "control_plane_primary_nav.html" not in admin_base:
        errors.append("templates/admin/base.html must include primary nav in manager header")
    cp_base = (REPO_ROOT / "templates/control_plane_base.html").read_text(encoding="utf-8")
    if 'data-rmc-cp-header-200x="1"' not in cp_base:
        errors.append("templates/control_plane_base.html must use cp-header 200x stack")
    cp_sk = (REPO_ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    if "rmc-cp-header-200x.css" not in cp_sk:
        errors.append("templates/control_plane_skeleton.html must load rmc-cp-header-200x.css")
    ticker_partial = (REPO_ROOT / "templates/partials/cockpit/_activity_ticker.html").read_text(
        encoding="utf-8"
    )
    if "cp-activity-ticker" not in ticker_partial:
        errors.append("_activity_ticker.html must expose cp-activity-ticker class for preview parity")
    topbar = (REPO_ROOT / "templates/partials/manager_operator_topbar.html").read_text(encoding="utf-8")
    if "_operator_presence.html" not in topbar:
        errors.append("manager_operator_topbar must include operator presence in utility row")
    if (
        "rmc-scroll-container.js" not in base_site
        and "rmc_platform_chrome_scripts.html" not in base_site
    ):
        errors.append(
            "templates/admin/base_site.html must load rmc_platform_chrome_scripts partial"
        )
    scroll_js = (REPO_ROOT / "static/js/rmc-scroll-container.js").read_text(encoding="utf-8")
    if 'mode === "document"' not in scroll_js and "mode === \"document\"" not in scroll_js:
        errors.append("static/js/rmc-scroll-container.js must handle data-rmc-cp-scroll=document")
    if "manager_platform_admin_sidebar.html" not in admin_base:
        errors.append("templates/admin/base.html must include manager_platform_admin_sidebar")
    if "<main id=\"cp-main-content\"" not in admin_base:
        errors.append("templates/admin/base.html must use <main> for #cp-main-content")
    if "control_plane_sidebar.html" in admin_base:
        errors.append(
            "templates/admin/base.html must not include control_plane_sidebar on manager admin"
        )
    parity_css = (REPO_ROOT / "static/css/admin-cp-parity.css").read_text(encoding="utf-8")
    if ".cp-sidebar-platform-admin" not in parity_css:
        errors.append("admin-cp-parity.css missing .cp-sidebar-platform-admin styles")
    return errors


def check_nav_builders() -> list[str]:
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory

    from apps.schools.control_plane_nav import build_control_plane_nav

    errors: list[str] = []
    request = RequestFactory().get("/super/")
    request.urlconf = "config.manager_urls"
    request.user = get_user_model()(is_superuser=True, username="nav_verify")
    advanced = next(
        (g for g in build_control_plane_nav(request) if g.get("label") == "Advanced"),
        None,
    )
    if not advanced:
        errors.append("control plane nav missing Advanced group")
        return errors
    for item in advanced.get("items") or []:
        url = item.get("url") or ""
        if "/super/admin-bridge/" in url:
            errors.append(
                f"Advanced nav must use direct admin URLs, not bridge: {item.get('id')}"
            )
    return errors


def check_render() -> list[str]:
    import django

    django.setup()
    from django.test import Client

    from scripts._manager_render_smoke import (
        MANAGER_HOST,
        ensure_manager_smoke_user,
        prepare_manager_smoke_client,
    )

    user = ensure_manager_smoke_user("manager_admin_cp_layout_verify")
    client = Client()
    client.force_login(user)
    prepare_manager_smoke_client(client)
    host = MANAGER_HOST
    probes: tuple[tuple[str, tuple[str, ...]], ...] = (
            (
                "/admin/",
                (
                    "admin-cp-unified-page",
                    "cp-admin-index",
                    "cp-catalog-card",
                    "Platform Backoffice",
                    'id="cp-main-content"',
                    "cp-admin-page-body",
                    'data-shell-nav-family="platform-admin"',
                    "data-rmc-platform-admin-sidebar",
                    "admin-sidebar-app-groups",
                    "cp-admin-sidebar-apps",
                    "cp-sidebar__group-toggle",
                    "data-rmc-admin-catalog-index",
                    "cp-hero__title",
                    'data-rmc-cp-header-200x="1"',
                    "cp-live-strip",
                    "cp-nav-row",
                    "cp-activity-ticker",
                    "cp-primary-nav",
                    "rmc-admin-v1-200x.css",
                    "rmc-cp-header-200x.css",
                ),
            ),
        (
            "/admin/accounts/user/",
            (
                "admin-cp-unified-page",
                'id="cp-main-content"',
                'data-shell-nav-family="platform-admin"',
                "results",
            ),
        ),
        (
            "/super/",
            (
                'data-shell-nav-family="control-plane"',
                "Advanced",
                'data-rmc-cp-header-200x="1"',
                "cp-live-strip",
                "cp-nav-row",
                "cp-activity-ticker",
                "cp-primary-nav",
                "rmc-cp-header-200x.css",
            ),
        ),
    )
    errors: list[str] = []
    for path, needles in probes:
        response = client.get(path, HTTP_HOST=host, secure=True)
        if response.status_code != 200:
            errors.append(f"{path}: HTTP {response.status_code}")
            continue
        html = response.content.decode("utf-8", errors="replace")
        for needle in needles:
            if needle not in html:
                errors.append(f"{path}: missing {needle!r} in HTML")
        live_pos = html.find("cp-live-strip")
        nav_pos = html.find("cp-nav-row")
        if path.startswith("/super"):
            if live_pos < 0 or nav_pos < 0 or live_pos > nav_pos:
                errors.append(
                    f"{path}: rendered header must stack cp-live-strip before cp-nav-row (v8 200x)"
                )
        elif path.startswith("/admin"):
            if live_pos < 0 or nav_pos < 0 or nav_pos > live_pos:
                errors.append(
                    f"{path}: rendered header must stack cp-nav-row before cp-live-strip (admin v1 200x)"
                )
    return errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--css-only",
        action="store_true",
        help="Skip HTTP render smoke (use in meta-runners; CI runs full check after migrate).",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Repository root override (passed by verify_phases_3_11_gates.py); ignored when unset.",
    )
    args = parser.parse_args()

    errors = check_css()
    if not args.css_only:
        try:
            errors.extend(check_nav_builders())
            errors.extend(check_render())
        except Exception as exc:  # pragma: no cover
            errors.append(f"render smoke failed: {exc}")
    if errors:
        print("verify_manager_admin_cp_layout: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("verify_manager_admin_cp_layout: OK (CSS guards + manager /admin/ smoke)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
