#!/usr/bin/env python3
"""Verify operator vs tenant theme/experience plane isolation (storage, views, templates)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    errors: list[str] = []

    plane_py = ROOT / "apps/siteconfig/theme_builder_plane.py"
    views_py = ROOT / "apps/siteconfig/views_theme_builder.py"
    hub_views = ROOT / "apps/siteconfig/views_theme_experience_hub.py"
    if not plane_py.is_file():
        errors.append("missing apps/siteconfig/theme_builder_plane.py")
    if not views_py.is_file():
        errors.append("missing apps/siteconfig/views_theme_builder.py")

    plane_src = plane_py.read_text(encoding="utf-8") if plane_py.is_file() else ""
    views_src = views_py.read_text(encoding="utf-8") if views_py.is_file() else ""
    hub_views_src = hub_views.read_text(encoding="utf-8") if hub_views.is_file() else ""

    for token in (
        "OPERATOR_RUNTIME_PAYLOAD_KEY",
        "TENANT_SCHOOL_SETTINGS_KEY",
        "OPERATOR_PUBLISH_LOG_KEY",
        "TENANT_PUBLISH_LOG_KEY",
        "persist_operator_brand_colors",
        "persist_tenant_brand_colors",
        "resolve_theme_builder_plane",
        "build_hub_glance_context",
        "record_publish_event",
        "assert_theme_colors_request_plane",
        "rollback_previous_publish",
        "build_publish_snapshot",
    ):
        if token not in plane_src:
            errors.append(f"theme_builder_plane.py missing {token}")

    if "theme_builder_control_plane.html" not in views_src:
        errors.append("views_theme_builder must render theme_builder_control_plane.html on operator plane")
    if "persist_operator_brand_colors" not in views_src:
        errors.append("publish API must route operator colors through persist_operator_brand_colors")
    if "persist_tenant_brand_colors" not in views_src:
        errors.append("publish API must route tenant colors through persist_tenant_brand_colors")
    if "record_publish_event" not in views_src:
        errors.append("views_theme_builder must record publish events per plane")
    if "ThemeBuilderRollbackAPIView" not in views_src:
        errors.append("views_theme_builder missing ThemeBuilderRollbackAPIView")
    urls_py = (ROOT / "apps/siteconfig/urls.py").read_text(encoding="utf-8", errors="replace")
    if "theme_builder_rollback_api" not in urls_py:
        errors.append("urls.py missing theme_builder_rollback_api")

    if "SiteSettings._persist_runtime_payload_updates" in views_src:
        errors.append(
            "views_theme_builder must not call SiteSettings._persist_runtime_payload_updates "
            "(use theme_builder_plane split)"
        )

    if "build_hub_glance_context" not in hub_views_src:
        errors.append("theme_experience_hub view must pass hub_glance context")
    if "Paginator" not in hub_views_src:
        errors.append("theme_experience_hub must paginate surfaces")

    views_py_main = (ROOT / "apps/siteconfig/views.py").read_text(encoding="utf-8", errors="replace")
    if "assert_theme_colors_request_plane" not in views_py_main:
        errors.append("theme_colors_page must call assert_theme_colors_request_plane")

    hub_body = (
        ROOT / "templates/siteconfig/partials/theme_experience_hub_body.html"
    ).read_text(encoding="utf-8", errors="replace")
    if 'data-rmc-plane="{% if operator_plane %}platform{% else %}tenant{% endif %}"' not in hub_body:
        errors.append("hub body missing data-rmc-plane marker")
    if "Platform operator" not in hub_body or "School tenant" not in hub_body:
        errors.append("hub body missing plane badges")
    if "rmc-cp-compact__fold-nav" not in hub_body:
        errors.append("hub body missing fold navigation")
    if "hub_glance" not in hub_body:
        errors.append("hub body missing glance strip")
    if "rmc-theme-hub-contrast-pill" not in hub_body:
        errors.append("hub body missing brand contrast pill")
    if "rmc-theme-hub-glance__chip" not in hub_body:
        errors.append("hub body missing glance color swatches")
    if "components/pagination.html" not in hub_body:
        errors.append("hub body missing pagination partial")

    cp_hub = ROOT / "templates/siteconfig/theme_experience_hub_control_plane.html"
    if cp_hub.is_file():
        cp_hub_src = cp_hub.read_text(encoding="utf-8", errors="replace")
        if "rmc-cp-compact-surface.css" not in cp_hub_src:
            errors.append("control plane hub missing compact surface CSS")
        if "theme-experience-premium.css" not in cp_hub_src:
            errors.append("control plane hub missing theme-experience-premium.css")

    cp_builder = ROOT / "templates/siteconfig/theme_builder_control_plane.html"
    if not cp_builder.is_file():
        errors.append("missing theme_builder_control_plane.html")
    elif 'data-rmc-plane="platform"' not in cp_builder.read_text(encoding="utf-8", errors="replace"):
        errors.append("operator builder template missing data-rmc-plane=platform")

    tenant_builder = ROOT / "templates/siteconfig/theme_builder.html"
    if tenant_builder.is_file():
        tb = tenant_builder.read_text(encoding="utf-8", errors="replace")
        if 'data-rmc-plane="tenant"' not in tb:
            errors.append("tenant builder template missing data-rmc-plane=tenant")

    surfaces_py = ROOT / "apps/siteconfig/theme_experience_surfaces.py"
    if surfaces_py.is_file():
        surfaces_src = surfaces_py.read_text(encoding="utf-8")
        if "def build_tenant_theme_experience_surfaces" not in surfaces_src:
            errors.append("theme_experience_surfaces missing build_tenant_theme_experience_surfaces")
        if "def build_platform_theme_experience_surfaces" not in surfaces_src:
            errors.append("theme_experience_surfaces missing build_platform_theme_experience_surfaces")

    hub_view = ROOT / "apps/siteconfig/views_theme_experience_hub.py"
    if hub_view.is_file():
        hub_src = hub_view.read_text(encoding="utf-8")
        if "theme_experience_hub_control_plane.html" not in hub_src:
            errors.append("hub view must use control_plane template on operator host")
        if "theme_experience_hub_tenant.html" not in hub_src:
            errors.append("hub view must use tenant template on tenant host")

    tests_py = ROOT / "apps/siteconfig/tests/test_theme_experience_plane_isolation.py"
    if not tests_py.is_file():
        errors.append("missing apps/siteconfig/tests/test_theme_experience_plane_isolation.py")

    sw = (ROOT / "static/js/service-worker.js").read_text(encoding="utf-8", errors="replace")
    sw_slugs = (
        "dual-plane-theme-experience",
        "theme-rollback-portal-bridge",
        "theme-dual-plane-ci-spine",
        "theme-dual-plane-apple-qa-e2e",
        "theme-experience-premium",
        "studio-guidance-tags",
        "tenant-studio-wizard",
        "tenant-studio-favicon-links",
        "studio-cockpit-day1-magic",
    )
    if "theme-dual-plane" not in sw and "theme-experience-premium" not in sw and not any(
        slug in sw for slug in sw_slugs
    ):
        errors.append(
            "service-worker CACHE_VERSION must bump for theme experience wave "
            f"(expected one of {sw_slugs})"
        )

    if errors:
        print("verify_theme_experience_plane_isolation: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("verify_theme_experience_plane_isolation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
