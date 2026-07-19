from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    portal_base = _read("templates/portal_base.html")
    control_plane_base = _read("templates/control_plane_base.html")
    admin_base_site = _read("templates/admin/base_site.html")
    studio_workspace = _read("templates/studio_os/components/workspace_layout.html")
    studio_css = _read("static/css/studio-workspace.css")
    tenant_canvas_css = _read("static/css/rmc-tenant-workspace-canvas.css")
    scroll_css_path = ROOT / "static/css/rmc-tenant-surface-scroll-contract.css"
    paginator_js_path = ROOT / "static/js/rmc-tenant-surface-paginator.js"
    scroll_css = scroll_css_path.read_text(encoding="utf-8", errors="replace") if scroll_css_path.exists() else ""
    paginator_js = paginator_js_path.read_text(encoding="utf-8", errors="replace") if paginator_js_path.exists() else ""

    portal_tokens = (
        "rmc-tenant-surface-scroll-contract.css",
        "?v=20260713-platform-pages",
        "rmc-tenant-surface-paginator.js",
        "rmc-section-nav.js",
        "data-rmc-cp-scroll",
        "id=\"main-content\"",
    )
    for token in portal_tokens:
        if token not in portal_base:
            errors.append(f"templates/portal_base.html missing {token}")

    control_plane_tokens = (
        "rmc-tenant-surface-scroll-contract.css",
        "?v=20260713-platform-pages",
        "rmc-tenant-surface-paginator.js",
        "id=\"cp-main-content\"",
        "data-rmc-cp-page-body=\"1\"",
    )
    for token in control_plane_tokens:
        if token not in control_plane_base:
            errors.append(f"templates/control_plane_base.html missing {token}")

    admin_tokens = (
        "rmc-tenant-surface-scroll-contract.css",
        "?v=20260719-tools-span-fix",
        "rmc-tenant-surface-paginator.js",
        "rmc-admin-django-canvas-contract.css",
    )
    for token in admin_tokens:
        if token not in admin_base_site:
            errors.append(f"templates/admin/base_site.html missing {token}")

    css_tokens = (
        "rmc-tenant-surface-pages",
        "rmc-surface-page-nav",
        "data-rmc-surface-page",
        "data-rmc-surface-scroll-zone=\"bounded\"",
        "max-height: clamp(22rem, 56vh, 44rem)",
        ".rmc-live-preview-contract",
        ".rmc-studio-workspace[data-rmc-studio-workspace=\"1\"]",
        "body:is(.control-plane-shell, .admin-manager-shell, .admin-premium-shell)",
        "[data-rmc-shell-root=\"django-admin\"]",
        "overflow-x: auto",
        "scroll-padding-block",
    )
    if not scroll_css_path.exists():
        errors.append("static/css/rmc-tenant-surface-scroll-contract.css is missing")
    for token in css_tokens:
        if token not in scroll_css:
            errors.append(f"rmc-tenant-surface-scroll-contract.css missing {token}")

    js_tokens = (
        "rmc-tenant-surface-paginator",
        "data-rmc-django-surface-canvas=\"tenant-backend\"",
        "data-rmc-shell-root=\"django-admin\"",
        "data-rmc-cp-page-body=\"1\"",
        "studio-os__canvas",
        "rmc-studio-workspace__main",
        "data-rmc-page=\"studio-os\"",
        "data-rmc-surface-page",
        "data-rmc-surface-scroll-zone",
        "Page ",
        "scrollIntoView",
        "hasExcludedPreview",
    )
    if not paginator_js_path.exists():
        errors.append("static/js/rmc-tenant-surface-paginator.js is missing")
    for token in js_tokens:
        if token not in paginator_js:
            errors.append(f"rmc-tenant-surface-paginator.js missing {token}")

    workspace_tokens = (
        'data-rmc-studio-workspace="1"',
        'data-rmc-studio-workspace-main="1"',
        "rmc-empty-state-sentinel",
        "data-rmc-scroll-policy=\"paginate\"",
    )
    for token in workspace_tokens:
        if token not in studio_workspace:
            errors.append(f"studio workspace layout missing {token}")

    existing_scroll_tokens = (
        "#main-content",
        "overflow-y: auto",
        "--rmc-tenant-main-h",
        ".portal-sidebar-col > .tp-sidebar-inner",
    )
    for token in existing_scroll_tokens:
        if token not in tenant_canvas_css:
            errors.append(f"rmc-tenant-workspace-canvas.css missing existing scroll contract {token}")

    studio_scroll_tokens = (
        ".rmc-studio-workspace__rail",
        "overflow: auto",
        "overscroll-behavior: contain",
        ".rmc-live-preview-contract__frame",
    )
    for token in studio_scroll_tokens:
        if token not in studio_css:
            errors.append(f"studio-workspace.css missing existing studio scroll contract {token}")

    if errors:
        print("TENANT_SURFACE_SCROLL_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("TENANT_SURFACE_SCROLL_CONTRACT_PASS")
    print("  scope: tenant portal + tenant backend + Studio work modes + operator /super/ + Django /admin/")
    print("  contract: single canvas scroll, long-page page nav, bounded list/table scroll zones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
