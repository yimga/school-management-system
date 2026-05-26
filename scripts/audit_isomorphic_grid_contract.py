#!/usr/bin/env python3
"""
Audit isomorphic design grid contract — viewport lock, spacing scale,
typographic guards, empty panels, and preview HTML alignment.

North-star references:
  - docs/generated/preview_app_shell_manager_v8_200x.html  → operator-control-plane
  - docs/generated/preview_app_shell_admin_v1_200x.html    → tenant-admin-hub (admin)
  - docs/generated/preview_app_shell_tenant_portal_v3_100x.html → tenant-admin-hub

Exits 0 with ISOMORPHIC_GRID_CONTRACT_PASS when wiring + markers are present.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/generated/isomorphic_grid_contract_audit.json"

ISO_CSS = "rmc-isomorphic-grid.css"
ISO_JS = "rmc-text-overflow-tooltip.js"
ISO_BOOT = "rmc_isomorphic_grid_boot.html"
ISO_EMPTY = "components/rmc_iso_empty_panel.html"

SHELL_TEMPLATE_ATTRS: dict[str, str] = {
    "templates/control_plane_skeleton.html": 'data-rmc-isomorphic-template="operator-control-plane"',
    "templates/portal_base.html": "data-rmc-isomorphic-template=",
    "templates/admin/base.html": "data-rmc-isomorphic-template=",
}

REQUIRED_CSS_MARKERS = (
    "--rmc-iso-grid-unit",
    "--rmc-iso-space-4",
    "data-rmc-isomorphic-template=\"operator-control-plane\"",
    "data-rmc-isomorphic-template=\"tenant-admin-hub\"",
    "data-rmc-isomorphic-template=\"onboarding-wizard\"",
    ".rmc-text-container",
    ".rmc-iso-panel-empty",
    ".rmc-iso-split-pane",
    ".rmc-iso-grid--3col",
)

REQUIRED_JS_MARKERS = (
    "data-rmc-text-overflow",
    "rmcTextOverflow",
    "markOverflowNodes",
)


def _read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def audit_css_bundle() -> list[str]:
    fails: list[str] = []
    css = _read(f"static/css/{ISO_CSS}")
    if not css:
        return [f"missing static/css/{ISO_CSS}"]
    for marker in REQUIRED_CSS_MARKERS:
        if marker not in css:
            fails.append(f"{ISO_CSS}: missing marker `{marker}`")
    return fails


def audit_js_bundle() -> list[str]:
    fails: list[str] = []
    js = _read(f"static/js/{ISO_JS}")
    if not js:
        return [f"missing static/js/{ISO_JS}"]
    for marker in REQUIRED_JS_MARKERS:
        if marker not in js:
            fails.append(f"{ISO_JS}: missing marker `{marker}`")
    if 'createElement("motion"' in js:
        fails.append(f"{ISO_JS}: corrupt createElement call")
    return fails


def audit_platform_wiring() -> list[str]:
    fails: list[str] = []
    chrome = _read("templates/partials/rmc_platform_chrome_styles.html")
    if ISO_CSS not in chrome:
        fails.append("rmc_platform_chrome_styles.html missing isomorphic grid CSS")

    boot = _read(f"templates/partials/{ISO_BOOT}")
    if ISO_JS not in boot:
        fails.append(f"{ISO_BOOT} missing {ISO_JS}")

    empty = _read(f"templates/{ISO_EMPTY}")
    if "rmc-iso-panel-empty" not in empty:
        fails.append(f"{ISO_EMPTY} missing rmc-iso-panel-empty root class")

    cp = _read("templates/control_plane_skeleton.html")
    if 'data-rmc-isomorphic-template="operator-control-plane"' not in cp:
        fails.append("control_plane_skeleton.html missing operator-control-plane template attr")
    if ISO_BOOT not in cp and ISO_JS not in cp:
        fails.append("control_plane_skeleton.html missing isomorphic grid boot script")

    portal = _read("templates/portal_base.html")
    if "data-rmc-isomorphic-template=" not in portal:
        fails.append("portal_base.html missing isomorphic template attr")
    if ISO_BOOT not in portal and ISO_JS not in portal:
        fails.append("portal_base.html missing isomorphic grid boot script")

    admin = _read("templates/admin/base.html")
    if "data-rmc-isomorphic-template=" not in admin:
        fails.append("admin/base.html missing isomorphic template attr")

    base = _read("templates/base.html")
    if "onboarding-wizard" not in base and ISO_BOOT not in base:
        fails.append("base.html missing onboarding-wizard template wiring")

    # Preview HTML north stars must still exist (grass audit dependency)
    for rel in (
        "docs/generated/preview_app_shell_manager_v8_200x.html",
        "docs/generated/preview_app_shell_admin_v1_200x.html",
        "docs/generated/preview_app_shell_tenant_portal_v3_100x.html",
    ):
        path = ROOT / rel
        if not path.is_file() or path.stat().st_size < 2048:
            fails.append(f"missing or corrupt preview north star: {rel}")

    return fails


def audit_app_shell_composition() -> list[str]:
    fails: list[str] = []
    app_shell = _read("static/css/rmc-app-shell.css")
    if "height: 100vh" not in app_shell and "100dvh" not in app_shell:
        fails.append("rmc-app-shell.css missing viewport height lock")
    iso = _read(f"static/css/{ISO_CSS}")
    if ".rmc-app-shell" not in iso:
        fails.append(f"{ISO_CSS} must compose on .rmc-app-shell")
    return fails


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    checks = {
        "css_bundle": audit_css_bundle(),
        "js_bundle": audit_js_bundle(),
        "platform_wiring": audit_platform_wiring(),
        "app_shell_composition": audit_app_shell_composition(),
    }
    failures: list[str] = []
    for items in checks.values():
        failures.extend(items)

    report = {
        "finding_count": len(failures),
        "findings": [{"message": m} for m in failures],
        "checks": {k: len(v) for k, v in checks.items()},
        "preview_north_stars": [
            "docs/generated/preview_app_shell_manager_v8_200x.html",
            "docs/generated/preview_app_shell_admin_v1_200x.html",
            "docs/generated/preview_app_shell_tenant_portal_v3_100x.html",
        ],
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "remediation_status": "PASS" if not failures else "FAIL",
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("ISOMORPHIC_GRID_CONTRACT_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("ISOMORPHIC_GRID_CONTRACT_PASS")
    print("  templates: operator-control-plane | tenant-admin-hub | onboarding-wizard")
    print("  preview north stars: manager v8 / admin v1 / tenant portal v3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
