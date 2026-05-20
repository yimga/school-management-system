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
)

# Tenant-only row layout must not apply to unified manager admin page.
ROW_LAYOUT_OK = re.compile(
    r"#page:not\(\.admin-cp-unified-page\)\s*\{[^}]*flex-direction:\s*row",
    re.DOTALL,
)
FIRST_CHILD_TRAP = re.compile(
    r"#page:not\(\.admin-cp-unified-page\)\s*>\s*div:first-child",
)
UNIFIED_COLUMN = re.compile(
    r"\.admin-cp-unified-page\s*\{[^}]*flex-direction:\s*column",
    re.DOTALL,
)
MAIN_SCROLL_CONTRACT = re.compile(
    r"body\.admin-manager-shell\[data-rmc-cp-scroll=\"main\"\].*#cp-main-content\s*\{[^}]*overflow-y:\s*auto",
    re.DOTALL,
)
MAIN_SCROLL_ALIGN = re.compile(
    r"body\.admin-manager-shell\[data-rmc-cp-scroll=\"main\"\].*#cp-main-content\s*\{[^}]*align-self:\s*stretch",
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
            if not MAIN_SCROLL_CONTRACT.search(text):
                errors.append(
                    f"{rel}: missing data-rmc-cp-scroll=main #cp-main-content overflow-y:auto contract"
                )
            if not MAIN_SCROLL_ALIGN.search(text):
                errors.append(
                    f"{rel}: missing data-rmc-cp-scroll=main align-self:stretch on #cp-main-content"
                )
    admin_base = (REPO_ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
    if "admin-cp-unified-page" not in admin_base:
        errors.append("templates/admin/base.html missing admin-cp-unified-page class")
    if "data-rmc-admin-cp-unified" not in admin_base:
        errors.append("templates/admin/base.html missing data-rmc-admin-cp-unified marker")
    if 'data-rmc-cp-scroll="main"' not in admin_base:
        errors.append("templates/admin/base.html missing data-rmc-cp-scroll=main on #page")
    base_site = (REPO_ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
    if "data-rmc-cp-scroll', 'main'" not in base_site:
        errors.append("templates/admin/base_site.html must set data-rmc-cp-scroll=main for manager admin")
    if "data-rmc-cp-scroll', 'document'" in base_site.split("if (isManager)")[1].split("} else {")[0]:
        errors.append(
            "templates/admin/base_site.html manager branch must not set data-rmc-cp-scroll=document"
        )
    scroll_js = (REPO_ROOT / "static/js/rmc-scroll-container.js").read_text(encoding="utf-8")
    if 'mode === "main"' not in scroll_js:
        errors.append("static/js/rmc-scroll-container.js must handle data-rmc-cp-scroll=main")
    if 'data-rmc-shell-main-scroll' not in admin_base:
        errors.append("templates/admin/base.html #cp-main-content missing data-rmc-shell-main-scroll")
    if "manager_platform_admin_sidebar.html" not in admin_base:
        errors.append("templates/admin/base.html must include manager_platform_admin_sidebar")
    if 'id="cp-main-content"' in admin_base and "min-h-0" not in admin_base.split('id="cp-main-content"')[1].split(">")[0]:
        errors.append(
            "templates/admin/base.html #cp-main-content must include min-h-0 for main-column scroll"
        )
    if "cp-admin-main-scroll-pane" not in admin_base:
        errors.append(
            "templates/admin/base.html missing cp-admin-main-scroll-pane wrapper for scroll chain"
        )
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
    from django.contrib.auth import get_user_model
    from django.test import Client

    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="manager_admin_cp_layout_verify",
        defaults={"is_staff": True, "is_superuser": True},
    )
    if not user.check_password("verify-pass"):
        user.set_password("verify-pass")
        user.save(update_fields=["password"])

    client = Client()
    client.force_login(user)
    host = "manager.runmycampus.com"
    probes: tuple[tuple[str, tuple[str, ...]], ...] = (
            (
                "/admin/",
                (
                    "admin-cp-unified-page",
                    "cp-admin-index",
                    "Platform Backoffice",
                    'id="cp-main-content"',
                    'data-rmc-cp-scroll="main"',
                    'data-shell-nav-family="platform-admin"',
                    "data-rmc-platform-admin-sidebar",
                    "admin-sidebar-all-apps",
                    "rmc-admin-catalog",
                    "Applications",
                ),
            ),
        (
            "/admin/schools/school/",
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
            ),
        ),
    )
    errors: list[str] = []
    for path, needles in probes:
        response = client.get(path, HTTP_HOST=host)
        if response.status_code != 200:
            errors.append(f"{path}: HTTP {response.status_code}")
            continue
        html = response.content.decode("utf-8", errors="replace")
        for needle in needles:
            if needle not in html:
                errors.append(f"{path}: missing {needle!r} in HTML")
    return errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--css-only",
        action="store_true",
        help="Skip HTTP render smoke (use in meta-runners; CI runs full check after migrate).",
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
