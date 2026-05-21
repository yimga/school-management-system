#!/usr/bin/env python3
"""Mechanical gate for batch 1286 theme-experience gear-up surfaces."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    errors: list[str] = []

    required = [
        ROOT / "templates/siteconfig/partials/theme_experience_hub_hero.html",
        ROOT / "scripts/verify_playwright_performance_budgets.mjs",
        ROOT / ".github/workflows/playwright-performance-budgets.yml",
        ROOT / "apps/siteconfig/views_theme_builder.py",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing: {path.relative_to(ROOT)}")

    urls_py = (ROOT / "apps/siteconfig/urls.py").read_text(encoding="utf-8")
    for needle in (
        "theme_builder_publish_api",
        "theme_builder_preview_api",
        "theme_builder_layout_api",
    ):
        if needle not in urls_py:
            errors.append(f"urls.py missing {needle}")

    append_only = (ROOT / "apps/platform_runtime/append_only.py").read_text(
        encoding="utf-8"
    )
    if "AppendOnlyQuerySet" not in append_only or "bulk delete" not in append_only:
        errors.append("append_only.py missing bulk-delete guard")

    theme_builder = (ROOT / "apps/siteconfig/theme_builder.py").read_text(encoding="utf-8")
    for block_type in ("announcement", "cta"):
        if f'"type": "{block_type}"' not in theme_builder:
            errors.append(f"theme_builder.py missing block type {block_type}")

    hub_body = (
        ROOT / "templates/siteconfig/partials/theme_experience_hub_body.html"
    ).read_text(encoding="utf-8")
    if "theme_experience_hub_hero.html" not in hub_body:
        errors.append("hub body must include theme_experience_hub_hero partial")

    canvas_partial = (
        ROOT / "templates/siteconfig/partials/theme_builder_canvas_body.html"
    ).read_text(encoding="utf-8")
    for btn_id in (
        "theme-builder-publish",
        "theme-builder-preview",
        "theme-builder-undo",
    ):
        if btn_id not in canvas_partial:
            errors.append(f"theme_builder_canvas_body.html missing #{btn_id}")
    for template_rel in (
        "templates/siteconfig/theme_builder.html",
        "templates/siteconfig/theme_builder_control_plane.html",
    ):
        partial_rel = "siteconfig/partials/theme_builder_canvas_body.html"
        builder_html = (ROOT / template_rel).read_text(encoding="utf-8")
        if partial_rel not in builder_html:
            errors.append(f"{template_rel} must include {partial_rel}")

    plane_py = (ROOT / "apps/siteconfig/theme_builder_plane.py").read_text(encoding="utf-8")
    if "build_hub_glance_context" not in plane_py:
        errors.append("theme_builder_plane.py missing build_hub_glance_context")

    canvas_js = (ROOT / "static/js/theme-builder-canvas.js").read_text(encoding="utf-8")
    for api_path in (
        "/siteconfig/theme-experience/builder/api/publish/",
        "/siteconfig/theme-experience/builder/api/preview/",
        "/siteconfig/theme-experience/builder/api/publish-log/",
        "/siteconfig/theme-experience/builder/api/rollback/",
    ):
        if api_path not in canvas_js:
            errors.append(f"theme-builder-canvas.js missing {api_path}")
    if "theme-builder-rollback" not in canvas_partial:
        errors.append("theme_builder_canvas_body.html missing #theme-builder-rollback")

    if errors:
        print("verify_theme_experience_gear: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("verify_theme_experience_gear: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
