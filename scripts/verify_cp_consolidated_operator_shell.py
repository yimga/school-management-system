#!/usr/bin/env python3
"""Gate: consolidated operator header partial + CSS wired on manager shells."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

REQUIRED_PARTIAL = REPO / "templates/partials/control_plane_unified_header.html"
REQUIRED_CSS = REPO / "static/css/rmc-cp-consolidated-operator-shell.css"
REQUIRED_INLINE_TICKER = REPO / "templates/partials/cockpit/_activity_ticker_inline.html"

SHELLS = (
    "templates/control_plane_base.html",
    "templates/control_plane_skeleton.html",
    "templates/portal_base.html",
    "templates/admin/base.html",
    "templates/admin/base_site.html",
)


def main() -> int:
    findings: list[str] = []

    for path in (REQUIRED_PARTIAL, REQUIRED_CSS, REQUIRED_INLINE_TICKER):
        if not path.is_file():
            findings.append(f"missing {path.relative_to(REPO)}")

    partial = REQUIRED_PARTIAL.read_text(encoding="utf-8") if REQUIRED_PARTIAL.is_file() else ""
    if partial and "cp-header--consolidated" not in partial:
        findings.append("control_plane_unified_header.html: missing cp-header--consolidated")
    if partial and "_activity_ticker_inline.html" not in partial:
        findings.append("control_plane_unified_header.html: missing inline ticker include")

    css = REQUIRED_CSS.read_text(encoding="utf-8") if REQUIRED_CSS.is_file() else ""
    if css and "--rmc-cp-unified-header-h" not in css:
        findings.append("rmc-cp-consolidated-operator-shell.css: missing header height token")

    for rel in SHELLS:
        text = (REPO / rel).read_text(encoding="utf-8")
        if "rmc-cp-consolidated-operator-shell.css" not in text and rel != "templates/admin/base.html":
            findings.append(f"{rel}: missing consolidated shell CSS")
        if rel == "templates/control_plane_base.html":
            if "control_plane_unified_header.html" not in text:
                findings.append("control_plane_base.html: must include unified header partial")
            if "control_plane_primary_nav.html" in text and "cp_shell_canvas_chrome" in text:
                canvas = text.split("cp_shell_canvas_chrome", 1)[1][:800]
                if "control_plane_primary_nav.html" in canvas:
                    findings.append(
                        "control_plane_base.html: primary nav must not remain in canvas chrome"
                    )

    contract = (REPO / "apps/platform_runtime/shell_contract.py").read_text(encoding="utf-8")
    if "cp_header_mode" not in contract:
        findings.append("shell_contract.py: missing cp_header_mode")

    if findings:
        print("CP_CONSOLIDATED_OPERATOR_SHELL_FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("CP_CONSOLIDATED_OPERATOR_SHELL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
