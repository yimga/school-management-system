#!/usr/bin/env python3
"""Static gate for visible backoffice scroll roots on /super/ and manager /admin/."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "static/css/rmc-backoffice-scroll-10x.css"
ADMIN_BASE_SITE = ROOT / "templates/admin/base_site.html"
CP_SKELETON = ROOT / "templates/control_plane_skeleton.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _after(text: str, first: str, second: str) -> bool:
    first_i = text.find(first)
    second_i = text.find(second)
    return first_i >= 0 and second_i >= 0 and second_i > first_i


def main() -> int:
    failures: list[str] = []
    if not CSS.is_file():
        failures.append("missing static/css/rmc-backoffice-scroll-10x.css")
    else:
        css = _read(CSS)
        required_tokens = (
            'body.control-plane-shell[data-rmc-cp-scroll="canvas"] .rmc-app-shell__canvas-body',
            'body.admin-manager-shell[data-rmc-cp-scroll="canvas"] .admin-cp-unified-page #cp-main-content.cp-admin-canvas-main',
            "overflow-y: scroll !important",
            "scrollbar-gutter: stable",
            "scrollbar-color: var(--rmc-backoffice-scrollbar-thumb) var(--rmc-backoffice-scrollbar-track)",
            "::-webkit-scrollbar-thumb",
            "--rmc-backoffice-scrollbar-size",
        )
        for token in required_tokens:
            if token not in css:
                failures.append(f"rmc-backoffice-scroll-10x.css missing {token}")
        if re.search(r"scrollbar-color:\s*transparent\s+transparent", css):
            failures.append("rmc-backoffice-scroll-10x.css must not hide scrollbar color")

    admin = _read(ADMIN_BASE_SITE)
    cp = _read(CP_SKELETON)
    if "rmc-backoffice-scroll-10x.css" not in admin:
        failures.append("templates/admin/base_site.html does not load rmc-backoffice-scroll-10x.css")
    if not _after(admin, "manager-corporate-footer.css", "rmc-backoffice-scroll-10x.css"):
        failures.append("admin manager scroll contract must load after manager-corporate-footer.css")
    if "rmc-backoffice-scroll-10x.css" not in cp:
        failures.append("templates/control_plane_skeleton.html does not load rmc-backoffice-scroll-10x.css")
    if not _after(cp, "rmc-platform-vertical-compact.css", "rmc-backoffice-scroll-10x.css"):
        failures.append("control-plane scroll contract must load after vertical compact CSS")

    if failures:
        print("BACKOFFICE_SCROLL_AFFORDANCE_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("BACKOFFICE_SCROLL_AFFORDANCE_PASS")
    print("  routes: /super/* canvas-body scroll, /admin/* main scroll")
    return 0


if __name__ == "__main__":
    sys.exit(main())
