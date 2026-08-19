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

CONSOLIDATED_HEADER_PARTIAL = "templates/partials/control_plane_unified_header.html"
ACTIVITY_TICKER_PARTIAL = "templates/partials/cockpit/_activity_ticker.html"
NAV_ROW_MARKERS = ("cp-nav-row", "cp-header__row--inline-chrome")

TEMPLATE_CHECKS: tuple[tuple[str, str, str], ...] = (
    (CONSOLIDATED_HEADER_PARTIAL, "cp_shell_header_ticker", "consolidated header ticker block"),
    (CONSOLIDATED_HEADER_PARTIAL, "cp-header--consolidated", "consolidated single-band header"),
    (ACTIVITY_TICKER_PARTIAL, "cp-live-strip", "activity ticker live strip"),
    ("templates/partials/manager_operator_topbar.html", "_activity_ticker_inline.html", "Tier-1 inline ticker in the utility band"),
    ("templates/control_plane_base.html", "control_plane_unified_header.html", "manager unified header include"),
    ("templates/admin/base.html", "control_plane_unified_header.html", "admin manager unified header include"),
    ("templates/portal_base.html", "tenant_primary_nav.html", "tenant primary nav include"),
    ("templates/portal_base.html", "tp-sidebar-inner", "tenant sidebar inner"),
    ("templates/partials/tenant_primary_nav.html", "tp-primary-nav", "tenant primary nav partial"),
)


def _read(rel: str) -> str:
    path = REPO / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _consolidated_operator_stack() -> str:
    return "\n".join(
        _read(rel)
        for rel in (
            CONSOLIDATED_HEADER_PARTIAL,
            ACTIVITY_TICKER_PARTIAL,
            "templates/partials/control_plane_primary_nav.html",
        )
    )


def _nav_row_pos(text: str) -> int:
    positions = [text.find(marker) for marker in NAV_ROW_MARKERS if marker in text]
    return min(positions) if positions else -1


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

    header = _read(CONSOLIDATED_HEADER_PARTIAL)
    ticker = _read(ACTIVITY_TICKER_PARTIAL)
    topbar = _read("templates/partials/manager_operator_topbar.html")
    if "cp-live-strip" not in ticker:
        errors.append("consolidated operator stack: missing cp-live-strip (_activity_ticker partial)")
    if "_activity_ticker_inline.html" not in topbar and "_activity_ticker_inline.html" not in header:
        errors.append("consolidated operator stack: missing Tier-1 inline ticker in the utility band")
    if "cp-header__row--inline-chrome" in header or "cp-header__row--live" in header:
        errors.append(
            "consolidated operator header: forbidden second-row LIVE/nav stack "
            "(Clean Header v2 — one utility band + inline ticker)"
        )

    cp_base = _read("templates/control_plane_base.html")
    if "control_plane_unified_header.html" not in cp_base:
        errors.append("control_plane_base.html: missing control_plane_unified_header include")

    admin_base = _read("templates/admin/base.html")
    if "control_plane_unified_header.html" not in admin_base:
        errors.append("admin/base.html: missing control_plane_unified_header include for manager host")

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
