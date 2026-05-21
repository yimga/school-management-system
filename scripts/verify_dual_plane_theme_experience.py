#!/usr/bin/env python3
"""Verify tenant + manager theme/experience configurability surfaces exist."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    errors: list[str] = []
    required = [
        ROOT / "apps/siteconfig/views_theme_experience_hub.py",
        ROOT / "apps/siteconfig/theme_experience_surfaces.py",
        ROOT / "apps/siteconfig/theme_builder_plane.py",
        ROOT / "templates/siteconfig/theme_experience_hub_control_plane.html",
        ROOT / "templates/siteconfig/theme_experience_hub_tenant.html",
        ROOT / "templates/siteconfig/theme_builder_control_plane.html",
        ROOT / "templates/siteconfig/partials/theme_experience_hub_body.html",
        ROOT / "templates/partials/control_plane_operator_brand_style.html",
        ROOT / "static/css/control-plane-operator-brand.css",
        ROOT / "apps/brand_experience/control_plane_brand_vars.py",
        ROOT
        / "apps/migration_cloud/migrations/0010_rename_migration_c_is_acti_a8f3b1_idx_migration_c_is_acti_c68d15_idx_and_more.py",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing required artifact: {path.relative_to(ROOT)}")

    catalog = (ROOT / "apps/platform_runtime/administration_catalog.py").read_text(
        encoding="utf-8"
    )
    views_py = (ROOT / "apps/siteconfig/views.py").read_text(encoding="utf-8")
    if "theme_experience_hub" not in catalog:
        errors.append("administration_catalog missing theme_experience_hub route")
    if "/siteconfig/theme-experience/hub/" not in catalog:
        errors.append("TENANT_CONFIGURATION_SECTIONS missing theme hub route")
    if "theme_experience_hub" not in views_py:
        errors.append("theme_experience_redirect must default to theme_experience_hub")
    if "studio=1" not in views_py:
        errors.append("theme_experience_redirect missing ?studio=1 escape hatch")

    skeleton = (ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    if "control_plane_operator_brand_style.html" not in skeleton:
        errors.append("control_plane_skeleton missing operator brand partial")
    if "control-plane-operator-brand.css" not in skeleton:
        errors.append("control_plane_skeleton missing operator brand stylesheet")

    cp = (ROOT / "apps/siteconfig/context_processors.py").read_text(encoding="utf-8")
    if "CONTROL_PLANE_BRAND_CSS_VARS" not in cp:
        errors.append("context_processors missing CONTROL_PLANE_BRAND_CSS_VARS")
    if "platform_palette" not in cp:
        errors.append("context_processors missing platform_palette")

    hub_body = (
        ROOT / "templates/siteconfig/partials/theme_experience_hub_body.html"
    ).read_text(encoding="utf-8")
    if "impersonation_url" not in hub_body:
        errors.append("hub body missing operator impersonation CTA")

    if errors:
        print("verify_dual_plane_theme_experience: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("verify_dual_plane_theme_experience: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
