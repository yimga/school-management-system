#!/usr/bin/env python3
"""SOVEREIGN-MULTI-PERSONALITY — layout token interpreter matrix gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

GATES = (
    "scripts/audit_isomorphic_grid_sweep.py",
    "scripts/verify_marketing_lane2_internal_audit.py",
)

REQUIRED = (
    "apps/platform_runtime/layout_personality_matrix.py",
    "apps/platform_runtime/regional_surface_tokens.py",
    "apps/platform_runtime/templatetags/rmc_layout_tokens.py",
    "static/css/rmc-layout-token-matrix.css",
    "static/js/rmc-wizard-viewport-cache.js",
    "templates/components/rmc_setup_wizard_viewport.html",
)


def main() -> int:
    findings: list[str] = []

    for rel in REQUIRED:
        if not (REPO / rel).is_file():
            findings.append(f"missing {rel}")

    partial = REPO / "templates/partials/shell_rmc_registry_html_attrs.html"
    if partial.is_file():
        text = partial.read_text(encoding="utf-8")
        if "data-rmc-personality-os" not in text:
            findings.append("shell_rmc_registry_html_attrs: missing data-rmc-personality-os")
        if "data-rmc-iso-viewport-lock" not in text:
            findings.append("shell_rmc_registry_html_attrs: missing viewport lock attr")
    else:
        findings.append("missing shell_rmc_registry_html_attrs.html")

    chrome = REPO / "templates/partials/rmc_platform_chrome_styles.html"
    if chrome.is_file() and "rmc-layout-token-matrix.css" not in chrome.read_text(encoding="utf-8"):
        findings.append("rmc_platform_chrome_styles.html missing layout-token-matrix CSS")

    contract = (REPO / "apps/platform_runtime/shell_contract.py").read_text(encoding="utf-8")
    if "personality_os" not in contract:
        findings.append("shell_contract.py missing personality_os")

    for shell in (
        "templates/portal_base.html",
        "templates/control_plane_skeleton.html",
        "templates/marketing/base_marketing.html",
    ):
        p = REPO / shell
        if not p.is_file():
            findings.append(f"missing {shell}")
            continue
        text = p.read_text(encoding="utf-8")
        if 'dir="{{' not in text and "dir=" not in text:
            findings.append(f"{shell}: missing dir= on <html>")
        if 'lang="{{' not in text and "lang=" not in text:
            findings.append(f"{shell}: missing lang= on <html>")

    drawer = REPO / "templates/partials/portal_row_detail_drawer.html"
    if drawer.is_file() and "data-rmc-detail-drawer" not in drawer.read_text(encoding="utf-8"):
        findings.append("portal_row_detail_drawer: missing data-rmc-detail-drawer")

    css = REPO / "static/css/rmc-layout-token-matrix.css"
    if css.is_file():
        css_text = css.read_text(encoding="utf-8")
        for marker in (
            "rmc-data-table--matrix-max5",
            "rmc-wizard-viewport",
            "rmc-text-shield",
        ):
            if marker not in css_text:
                findings.append(f"rmc-layout-token-matrix.css: missing {marker}")

    for rel in GATES:
        proc = subprocess.run(
            [sys.executable, str(REPO / rel)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            findings.append(f"{rel} failed:\n{proc.stderr or proc.stdout}")

    if findings:
        print("verify_sovereign_layout_token_matrix: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_sovereign_layout_token_matrix: SOVEREIGN_LAYOUT_TOKEN_MATRIX_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
