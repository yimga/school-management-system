#!/usr/bin/env python3
"""Platform audit — row detail drawer wiring, duplicates, dismiss contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"

SHELL_FILES = {
    "control_plane": TEMPLATES / "control_plane_skeleton.html",
    "portal": TEMPLATES / "portal_base.html",
    "tenant_base": TEMPLATES / "base.html",
}
ADMIN_BASE = TEMPLATES / "admin" / "base_site.html"
BUNDLE_TEMPLATE = TEMPLATES / "partials" / "portal_row_detail_drawer_bundle.html"

BUNDLE = "portal_row_detail_drawer_bundle.html"
JS = REPO / "static" / "js" / "rmc-portal-row-detail-drawer.js"


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    js_text = JS.read_text(encoding="utf-8", errors="replace")
    for needle in (
        "window.rmcRowDetailDismiss",
        "data-rmc-portal-row-detail-dismiss",
        "hidden.bs.offcanvas",
        "dedupeDrawerDom",
        "rmcPortalRowDetailDrawerLoaded",
    ):
        if needle not in js_text:
            failures.append(f"JS missing {needle!r}")

    for name, path in SHELL_FILES.items():
        if not path.is_file():
            failures.append(f"Missing shell {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if BUNDLE not in text:
            failures.append(f"Shell {name} ({path.name}) missing {BUNDLE}")

    admin_text = ADMIN_BASE.read_text(encoding="utf-8", errors="replace")
    if BUNDLE in admin_text or "rmc-portal-row-detail-drawer.css" in admin_text:
        failures.append("Django admin must not mount the global portal row-detail drawer")

    bundle_text = BUNDLE_TEMPLATE.read_text(encoding="utf-8", errors="replace")
    if "{% if rmc_row_drawer_css_in_head %}" not in bundle_text:
        failures.append("Drawer bundle must render only when the root shell owns its head CSS")
    if '<link rel="stylesheet"' in bundle_text:
        failures.append("Drawer bundle must not emit a stylesheet from body")

    cp_dupes: list[str] = []
    table_pages = 0
    explicit_row_pages = 0
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if 'data-rmc-row-detail-table="1"' in text:
            table_pages += 1
        if 'data-rmc-row-detail="1"' in text:
            explicit_row_pages += 1
        extends_cp = "extends \"control_plane_base.html\"" in text or "extends 'control_plane_base.html'" in text
        if extends_cp and BUNDLE in text:
            rel = path.relative_to(REPO).as_posix()
            cp_dupes.append(rel)

    operator_pages = [
        TEMPLATES / "schools" / "super_schools_list.html",
        TEMPLATES / "schools" / "super_operator_team_roster.html",
        TEMPLATES / "schools" / "super_offboarding_queue.html",
    ]
    for path in operator_pages:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(REPO).as_posix()
        if BUNDLE in text:
            failures.append(f"{rel} must not include {BUNDLE} (shell provides it)")
        for attr in ('data-rmc-row-detail-table="1"', 'data-rmc-row-detail="1"'):
            if attr not in text:
                failures.append(f"{rel} missing {attr}")
        if "data-rmc-portal-row-detail-dismiss" in text:
            failures.append(f"{rel} should not embed dismiss markup (partial provides it)")

    lens_pages = [
        ("super_schools_list.html", "operator-schools-roster", "data-rmc-row-lens-api"),
        ("super_operator_team_roster.html", "operator-team-roster", "data-rmc-row-lens-api"),
        ("super_offboarding_queue.html", "operator-offboarding-queue", "data-rmc-row-lens-api"),
    ]
    for fname, lens, lens_attr in lens_pages:
        text = (TEMPLATES / "schools" / fname).read_text(encoding="utf-8", errors="replace")
        if f'data-rmc-copilot-page-lens="{lens}"' not in text:
            failures.append(f"{fname} missing copilot lens key {lens!r}")
        if lens_attr not in text:
            failures.append(f"{fname} missing {lens_attr}")

    # Copilot lens dismiss bridge
    lens_js = (REPO / "static" / "js" / "rmc-copilot-context-lens.js").read_text(
        encoding="utf-8", errors="replace"
    )
    if "window.rmcRowDetailDismiss" not in lens_js:
        failures.append("rmc-copilot-context-lens.js must delegate dismiss to rmcRowDetailDismiss")

    print("ROW DETAIL DRAWER PLATFORM AUDIT")
    print(f"  Templates with data-rmc-row-detail-table: {table_pages}")
    print(f"  Templates with explicit data-rmc-row-detail rows: {explicit_row_pages}")
    print(f"  Legacy control-plane bundle includes (render-safe no-ops): {len(cp_dupes)}")

    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(w)

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  {f}")
        print(f"\nAUDIT FAIL ({len(failures)} issue(s))")
        return 1

    print("\nAUDIT PASS — platform row-detail drawer ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
