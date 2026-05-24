#!/usr/bin/env python3
"""Non-negotiable gate: canonical preview HTML shells are implemented in production.

Validates the three operator-facing preview artifacts registered in
``apps.siteconfig.views_cockpit_previews.PREVIEWS`` are present on disk and
that production Django shells + CSS bundles implement their structural grammar.

This is stricter than ``verify_platform_shell_preview_parity.py`` (wiring only).
Legacy preview files under ``docs/generated/`` are listed as superseded; they
must not appear in PREVIEWS or production includes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Canonical previews (slug → filename) — single source mirrors views_cockpit_previews.
CANONICAL_PREVIEWS: dict[str, str] = {
    "admin-v1-200x": "preview_app_shell_admin_v1_200x.html",
    "manager-v8-200x": "preview_app_shell_manager_v8_200x.html",
    "tenant-portal-v3-100x": "preview_app_shell_tenant_portal_v3_100x.html",
}

SUPERSEDED_PREVIEW_FILES: tuple[str, ...] = (
    "preview_app_shell_manager.html",
    "preview_app_shell_tenant_portal.html",
    "preview_app_shell_tenant_portal_v2.html",
    "preview_app_shell_tenant_portal_v3.html",
    "preview_app_shell_super_v8_200x.html",
)

# Production implementation contract per canonical preview.
IMPLEMENTATION: dict[str, dict] = {
    "admin-v1-200x": {
        "label": "Platform /admin/ (manager host)",
        "templates": (
            ("templates/admin/base.html", ("cp-header", "cp-nav-row", "cp-live-strip", 'data-rmc-cp-header-200x="1"')),
            ("templates/admin/base_site.html", ("rmc-admin-v1-200x.css", "rmc-cp-header-200x.css", "rmc-cp-sidebar-200x.css")),
            ("templates/admin/index_superadmin.html", ("cp-hero", "cp-steering", "cp-kpi-strip", "cp-catalog-card", "data-rmc-admin-catalog-index", "admin_v1_index_surface_previews", "rmc-page-fold-nav", "rmc-admin-catalog-section")),
            ("templates/admin/partials/admin_v1_index_surface_previews.html", ("cp-changelist", "cp-form-frame", "cp-platform-tag-row")),
            ("templates/admin/base_site.html", ("help_contextual_drawer.html",)),
            ("templates/partials/help_contextual_drawer.html", ("Need help on this page?",)),
            ("templates/partials/manager_platform_admin_sidebar.html", ("cp-sidebar-platform-admin", "data-rmc-platform-admin-sidebar")),
        ),
        "order_checks": (
            ("templates/admin/base.html", "cp-live-strip", "cp-nav-row"),
        ),
        "css_files": (
            "static/css/rmc-admin-v1-200x.css",
            "static/css/rmc-cp-header-200x.css",
            "static/css/rmc-cp-sidebar-200x.css",
        ),
        "css_selectors": (
            "static/css/rmc-admin-v1-200x.css",
            (".cp-hero", ".cp-steering", ".cp-kpi", ".cp-catalog-card", ".cp-tab", ".cp-changelist", ".cp-form-frame"),
        ),
        "preview_markers": ("cp-nav-row", "cp-live-strip", "cp-hero", "cp-catalog-card"),
    },
    "manager-v8-200x": {
        "label": "Control plane /super/ (manager host)",
        "templates": (
            ("templates/control_plane_base.html", ("cp-header", "cp-nav-row", "cp-live-strip", 'data-rmc-cp-header-200x="1"')),
            ("templates/control_plane_skeleton.html", ("rmc-cp-header-200x.css", "rmc-cp-sidebar-200x.css", "rmc-platform-inner-pages.css")),
            ("templates/partials/control_plane_primary_nav.html", ("cp-primary-nav",)),
            ("templates/control_plane_skeleton.html", ("help_contextual_drawer.html",)),
            ("templates/partials/cockpit/_activity_ticker.html", ("cp-activity-ticker",)),
            ("templates/partials/manager_operator_topbar.html", ("cp-brand__tagline", "cp-header-search")),
        ),
        "order_checks": (
            ("templates/control_plane_base.html", "cp-live-strip", "cp-nav-row"),
        ),
        "css_files": (
            "static/css/rmc-cp-header-200x.css",
            "static/css/rmc-cp-sidebar-200x.css",
            "static/css/rmc-cp-200x.css",
            "static/css/rmc-platform-inner-pages.css",
        ),
        "css_selectors": (
            "static/css/rmc-cp-header-200x.css",
            (".cp-primary-nav", ".cp-activity-ticker", ".cp-live-strip", ".cp-nav-row"),
        ),
        "preview_markers": ("cp-primary-nav", "cp-activity-ticker", "cp-header__row--utility"),
    },
    "tenant-portal-v3-100x": {
        "label": "Tenant portal shell",
        "templates": (
            ("templates/portal_base.html", ("tp-header", "tenant_primary_nav.html", "tp-sidebar-inner", "rmc-tenant-header-100x.css", "rmc-tenant-canvas-100x.css", "rmc-civic-footer.css")),
            ("templates/partials/tenant_primary_nav.html", ("tp-primary-nav", "tp-primary-nav__item")),
            ("templates/portal_base.html", ("help_contextual_drawer.html",)),
            ("templates/partials/help_contextual_drawer.html", ("Need help on this page?",)),
            ("templates/partials/cockpit/_community_band.html", ("rmc-cband", "community_band")),
            ("templates/partials/cockpit/_newsletter_band.html", ("rmc-newsletter-band", "newsletter_band")),
        ),
        "order_checks": (),
        "css_files": (
            "static/css/rmc-tenant-header-100x.css",
            "static/css/rmc-tenant-canvas-100x.css",
            "static/css/rmc-civic-footer.css",
        ),
        "css_selectors": (
            (
                "static/css/rmc-tenant-header-100x.css",
                (".tp-primary-nav", ".tp-header"),
            ),
            (
                "static/css/rmc-cp-sidebar-200x.css",
                (".tp-sidebar-inner",),
            ),
        ),
        "preview_markers": ("tp-primary-nav", "tp-sidebar-inner", "tp-header"),
    },
}


def _read(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _previews_from_source() -> dict[str, dict[str, str]]:
    """Parse PREVIEWS slugs/filenames without importing Django views."""
    text = _read("apps/siteconfig/views_cockpit_previews.py")
    found: dict[str, dict[str, str]] = {}
    slug = ""
    for line in text.splitlines():
        m_slug = re.match(r'\s+"([a-z0-9-]+)":\s*\{', line)
        if m_slug:
            slug = m_slug.group(1)
            found.setdefault(slug, {})
            continue
        if slug:
            m_fn = re.search(r'"filename":\s*"([^"]+)"', line)
            if m_fn:
                found[slug]["filename"] = m_fn.group(1)
    return found


def _check_registry() -> list[str]:
    errors: list[str] = []
    previews = _previews_from_source()
    for slug, filename in CANONICAL_PREVIEWS.items():
        meta = previews.get(slug)
        if not meta:
            errors.append(f"PREVIEWS missing slug: {slug}")
            continue
        if meta.get("filename") != filename:
            errors.append(
                f"PREVIEWS[{slug}] filename drift: {meta.get('filename')!r} != {filename!r}"
            )
    for slug in previews:
        if slug not in CANONICAL_PREVIEWS:
            errors.append(f"PREVIEWS has unlisted slug (add to CANONICAL_PREVIEWS): {slug}")
    return errors


def _check_preview_files() -> list[str]:
    errors: list[str] = []
    preview_dir = REPO / "docs" / "generated"
    for slug, filename in CANONICAL_PREVIEWS.items():
        path = preview_dir / filename
        if not path.is_file():
            errors.append(f"missing canonical preview: docs/generated/{filename} ({slug})")
            continue
        if path.stat().st_size < 1024:
            errors.append(f"preview too small (corrupt?): {filename}")
        text = path.read_text(encoding="utf-8", errors="replace")
        contract = IMPLEMENTATION[slug]
        for marker in contract["preview_markers"]:
            if marker not in text:
                errors.append(f"preview {filename}: missing marker {marker}")
    return errors


def _check_superseded_not_wired() -> list[str]:
    errors: list[str] = []
    previews = _previews_from_source()
    for slug, meta in previews.items():
        fn = meta.get("filename") or ""
        if fn in SUPERSEDED_PREVIEW_FILES:
            errors.append(f"PREVIEWS[{slug}] still points at superseded file: {fn}")
    # Production must not include legacy preview paths.
    for rel in (
        "templates/control_plane_base.html",
        "templates/portal_base.html",
        "templates/admin/base_site.html",
    ):
        text = _read(rel)
        for legacy in SUPERSEDED_PREVIEW_FILES:
            if legacy in text:
                errors.append(f"{rel}: references superseded preview {legacy}")
    return errors


def _check_implementations() -> list[str]:
    errors: list[str] = []
    for slug, contract in IMPLEMENTATION.items():
        for rel, needles in contract["templates"]:
            text = _read(rel)
            if not text:
                errors.append(f"[{slug}] missing template: {rel}")
                continue
            for needle in needles:
                if needle not in text:
                    errors.append(f"[{slug}] {rel}: missing {needle}")
        for rel, first, second in contract["order_checks"]:
            text = _read(rel)
            p1, p2 = text.find(first), text.find(second)
            if p1 < 0 or p2 < 0 or p1 > p2:
                errors.append(
                    f"[{slug}] {rel}: production order requires {first} before {second}"
                )
        for css_rel in contract["css_files"]:
            if not (REPO / css_rel).is_file():
                errors.append(f"[{slug}] missing CSS bundle: {css_rel}")
        css_selector_groups = contract["css_selectors"]
        if (
            len(css_selector_groups) == 2
            and isinstance(css_selector_groups[0], str)
        ):
            css_selector_groups = (css_selector_groups,)
        for css_rel, selectors in css_selector_groups:
            css_text = _read(css_rel)
            if not css_text:
                errors.append(f"[{slug}] missing CSS for selectors: {css_rel}")
                continue
            for sel in selectors:
                if sel not in css_text:
                    errors.append(f"[{slug}] {css_rel}: missing rule for {sel}")
    return errors


def _check_platform_admin_index() -> list[str]:
    errors: list[str] = []
    text = _read("config/admin.py")
    if 'index_template_name = "admin/index_superadmin.html"' not in text:
        if "index_template_name" in text and "index_superadmin" not in text:
            errors.append(
                "config/admin.py: PlatformAdminSite must set "
                'index_template_name = "admin/index_superadmin.html"'
            )
        elif "index_superadmin" not in text:
            errors.append("config/admin.py: missing index_superadmin index template wiring")
    return errors


def _check_render_smoke() -> list[str]:
    errors: list[str] = []
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("DJANGO_LOG_FILE", os.devnull)
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.test import Client

    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="preview_html_impl_verify",
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
            ("cp-hero", "cp-catalog-card", "cp-nav-row", "cp-live-strip", "rmc-admin-v1-200x.css"),
        ),
        (
            "/super/",
            ("cp-primary-nav", "cp-activity-ticker", "cp-nav-row", "cp-live-strip"),
        ),
        (
            "/siteconfig/super/configure/cockpit/previews/",
            ("manager-v8-200x", "admin-v1-200x", "tenant-portal-v3-100x"),
        ),
    )
    for slug, filename in CANONICAL_PREVIEWS.items():
        probes = probes + (
            (
                f"/siteconfig/super/configure/cockpit/previews/{slug}/",
                ("<!doctype html", "<html"),
            ),
        )

    for path, needles in probes:
        response = client.get(path, HTTP_HOST=host, secure=True)
        if response.status_code != 200:
            errors.append(f"render smoke {path}: HTTP {response.status_code}")
            continue
        body = response.content.decode("utf-8", errors="replace").lower()
        for needle in needles:
            if needle.lower() not in body:
                errors.append(f"render smoke {path}: missing {needle}")
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_registry())
    errors.extend(_check_preview_files())
    errors.extend(_check_superseded_not_wired())
    errors.extend(_check_implementations())
    errors.extend(_check_platform_admin_index())
    errors.extend(_check_render_smoke())

    if errors:
        print("ALL_PREVIEW_SHELL_HTML_IMPLEMENTATION_FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("ALL_PREVIEW_SHELL_HTML_IMPLEMENTATION_PASS")
    print(f"  canonical previews: {len(CANONICAL_PREVIEWS)}")
    print(f"  superseded artifacts (not wired): {len(SUPERSEDED_PREVIEW_FILES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
