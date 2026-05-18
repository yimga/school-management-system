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
    admin_base = (REPO_ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
    if "admin-cp-unified-page" not in admin_base:
        errors.append("templates/admin/base.html missing admin-cp-unified-page class")
    if "data-rmc-admin-cp-unified" not in admin_base:
        errors.append("templates/admin/base.html missing data-rmc-admin-cp-unified marker")
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
                'id="cpSidebarNav"',
            ),
        ),
        (
            "/admin/schools/school/",
            (
                "admin-cp-unified-page",
                'id="cp-main-content"',
                "results",
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
