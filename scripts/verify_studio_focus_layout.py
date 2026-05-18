#!/usr/bin/env python3
"""
Wave 1 gate: manager Studio OS uses focus layout (compact sidebar, no full CP nav).

Checks shell_control_plane.html, studio-focus CSS, sidebar partial, and nav helper.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    findings: list[str] = []

    shell_cp = ROOT / "templates/studio_os/shell_control_plane.html"
    if shell_cp.is_file():
        text = shell_cp.read_text(encoding="utf-8", errors="replace")
        for needle in (
            'data-rmc-studio-focus="1"',
            "studio-focus-layout.css",
            "control_plane_sidebar_studio_focus.html",
            "block rmc_zero_click_strip",
        ):
            if needle not in text:
                findings.append(f"shell_control_plane.html missing {needle!r}")
        if "control_plane_sidebar.html" in text and "studio_focus" not in text:
            findings.append(
                "shell_control_plane.html must not include full control_plane_sidebar"
            )
    else:
        findings.append("missing templates/studio_os/shell_control_plane.html")

    css = ROOT / "static/css/studio-focus-layout.css"
    if not css.is_file():
        findings.append("missing static/css/studio-focus-layout.css")
    elif "[data-rmc-studio-focus=" not in css.read_text(encoding="utf-8"):
        findings.append("studio-focus-layout.css missing focus selectors")

    partial = ROOT / "templates/partials/control_plane_sidebar_studio_focus.html"
    if not partial.is_file():
        findings.append("missing control_plane_sidebar_studio_focus.html")
    elif "STUDIO_FOCUS_SIDEBAR" not in partial.read_text(encoding="utf-8"):
        findings.append("studio focus sidebar must iterate STUDIO_FOCUS_SIDEBAR")

    nav_py = ROOT / "apps/schools/control_plane_nav.py"
    if nav_py.is_file():
        nav_text = nav_py.read_text(encoding="utf-8", errors="replace")
        for fn in ("build_studio_focus_sidebar", "is_manager_studio_focus_path"):
            if f"def {fn}" not in nav_text:
                findings.append(f"control_plane_nav.py missing {fn}")
    else:
        findings.append("missing apps/schools/control_plane_nav.py")

    base = ROOT / "templates/control_plane_base.html"
    if base.is_file() and "block cp_layout_attrs" not in base.read_text(encoding="utf-8"):
        findings.append("control_plane_base.html missing cp_layout_attrs block")

    if findings:
        print(f"verify_studio_focus_layout: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("verify_studio_focus_layout: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
