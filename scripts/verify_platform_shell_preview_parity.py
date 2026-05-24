#!/usr/bin/env python3
"""Gate: platform shell preview parity (/super/, /admin/, tenant portal)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED_CSS = (
    "static/css/rmc-cp-header-200x.css",
    "static/css/rmc-cp-sidebar-200x.css",
    "static/css/rmc-platform-inner-pages.css",
    "static/css/rmc-admin-v1-200x.css",
    "static/css/rmc-tenant-header-100x.css",
    "static/css/rmc-tenant-canvas-100x.css",
)

TEMPLATE_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("templates/control_plane_base.html", "cp-live-strip", "cp-live-strip before nav row"),
    ("templates/control_plane_base.html", "cp-live-strip", "cp-live-strip wrapper"),
    ("templates/admin/base.html", "cp-nav-row", "admin header nav row"),
    ("templates/admin/base.html", "cp-live-strip", "admin header live strip"),
    ("templates/portal_base.html", "tenant_primary_nav.html", "tenant primary nav include"),
    ("templates/portal_base.html", "tp-sidebar-inner", "tenant sidebar inner"),
    ("templates/partials/tenant_primary_nav.html", "tp-primary-nav", "tenant primary nav partial"),
)


def main() -> int:
    errors: list[str] = []
    for rel in REQUIRED_CSS:
        if not (REPO / rel).is_file():
            errors.append(f"missing CSS: {rel}")

    for rel, needle, label in TEMPLATE_CHECKS:
        path = REPO / rel
        if not path.is_file():
            errors.append(f"missing template: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle not in text:
            errors.append(f"{rel}: missing {label} ({needle})")

    cp_base = (REPO / "templates/control_plane_base.html").read_text(encoding="utf-8", errors="replace")
    nav_pos = cp_base.find("cp-nav-row")
    live_pos = cp_base.find("cp-live-strip")
    if nav_pos < 0 or live_pos < 0 or live_pos > nav_pos:
        errors.append(
            "control_plane_base.html: cp-live-strip must precede cp-nav-row (v8 200x manager stack)"
        )

    admin_base = (REPO / "templates/admin/base.html").read_text(encoding="utf-8", errors="replace")
    an = admin_base.find("cp-nav-row")
    al = admin_base.find("cp-live-strip")
    if an < 0 or al < 0 or an > al:
        errors.append(
            "admin/base.html: cp-nav-row must precede cp-live-strip (admin v1 200x: utility → nav → live strip)"
        )

    previews = REPO / "docs/generated"
    for name in (
        "preview_app_shell_admin_v1_200x.html",
        "preview_app_shell_manager_v8_200x.html",
        "preview_app_shell_tenant_portal_v3_100x.html",
    ):
        if not (previews / name).is_file():
            errors.append(f"missing preview artifact: docs/generated/{name}")

    if errors:
        print("PLATFORM_SHELL_PREVIEW_PARITY_FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("PLATFORM_SHELL_PREVIEW_PARITY_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
