#!/usr/bin/env python3
"""Platform chrome sweep — document scroll + sticky chrome on all public shells."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    errors: list[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            errors.append(msg)

    css = _read("static/css/rmc-platform-chrome-layout.css")
    need("portal-body-with-layout[data-rmc-cp-scroll=\"document\"]" in css, "tenant portal document scroll CSS")
    need("mkt-platform-header" in css, "marketing sticky header CSS")
    need("topbar-icon-badge" in css, "portal topbar badge containment CSS")
    need("position: sticky !important" in css, "sticky control-plane chrome uses !important")
    need("transform: none !important" in css, "bell badge transform reset")

    mcp = _read("static/css/manager-control-plane.css")
    doc_sidebar_marker = (
        'body.control-plane-shell[data-rmc-cp-scroll="document"] .cp-sidebar-col'
    )
    if doc_sidebar_marker in mcp:
        doc_sidebar_block = mcp.split(doc_sidebar_marker, 1)[1].split("}", 1)[0]
        need(
            "position: relative" not in doc_sidebar_block
            and "max-height: none" not in doc_sidebar_block,
            "manager-control-plane must not override document-scroll sidebar sticky",
        )

    super_tpl = _read("templates/schools/super_dashboard.html")
    need("{% block cp_workspace_header %}{% endblock %}" in super_tpl, "super_dashboard suppresses workspace strip")
    need(
        "rmc_platform_chrome_styles.html" not in super_tpl,
        "super_dashboard must not duplicate chrome partial (inherits skeleton)",
    )

    portal = _read("templates/portal_base.html")
    need('data-rmc-cp-scroll="document"' in portal, "portal_base sets document scroll on body")
    need("data-rmc-page-fold-nav=\"required\"" in portal and "portal-page-body" in portal, "portal page fold nav")

    marketing = _read("templates/marketing/base_marketing.html")
    need("rmc_platform_chrome_styles.html" in marketing, "marketing includes chrome styles partial")
    need("back_to_top.html" in marketing, "marketing loads back-to-top")
    need("rmc-page-fold-standards.js" in marketing, "marketing loads fold standards JS")

    admin_base = _read("templates/admin/base.html")
    need("127.0.0.1:7426" not in admin_base, "admin/base.html must not ship debug ingest")

    assist = _read("static/js/rmc-assist-dock.js")
    need("127.0.0.1:7426" not in assist, "rmc-assist-dock.js must not ship debug ingest")

    topo = _read("static/css/dashboard-topology-shell.css")
    need("portal-body-with-layout[data-rmc-cp-scroll=\"document\"]" in topo, "topology allows portal document scroll")

    offset = _read("static/js/rmc-cp-chrome-offset.js")
    need("portalHeader" in offset and "mkt-platform-header" in offset, "chrome offset measures all headers")

    premium = _read("static/css/rmc-platform-chrome-premium.css")
    need("rmc-chrome-glass" in premium or "--rmc-chrome-glass" in premium, "premium chrome CSS exists")
    need(_read("static/js/rmc-cp-chrome-scroll-polish.js").strip(), "chrome scroll polish JS exists")

    style_partial = _read("templates/partials/rmc_platform_chrome_styles.html")
    need("rmc-platform-chrome-premium.css" in style_partial, "chrome styles partial bundles premium CSS")
    need("dashboard-topology-shell.css" in style_partial, "chrome styles partial bundles topology CSS")

    for rel in (
        "templates/control_plane_skeleton.html",
        "templates/admin/base_site.html",
        "templates/portal_base.html",
        "templates/marketing/base_marketing.html",
        "templates/base.html",
    ):
        body = _read(rel)
        need(
            "rmc_platform_chrome_styles.html" in body,
            f"{rel} includes platform chrome styles partial",
        )

    for rel in (
        "templates/portal_base.html",
        "templates/admin/base_site.html",
        "templates/marketing/base_marketing.html",
        "templates/base.html",
        "templates/control_plane_skeleton.html",
    ):
        body = _read(rel)
        need(
            "rmc_platform_chrome_scripts.html" in body,
            f"{rel} includes platform chrome scripts partial",
        )

    need(
        'data-rmc-cp-scroll="document"' in _read("templates/base.html"),
        "base.html uses document scroll",
    )
    need(
        'data-rmc-cp-scroll="document"' in _read("templates/marketing/base_marketing.html"),
        "marketing uses document scroll",
    )

    if errors:
        print("verify_platform_chrome_sweep: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("verify_platform_chrome_sweep: OK (all canonical shells + chrome partials)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
