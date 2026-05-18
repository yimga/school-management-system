#!/usr/bin/env python3
"""Wave 4 gate: inlined feature control in Studio Control mode strips duplicate chrome."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    findings: list[str] = []

    css = ROOT / "static/css/studio-control-inline.css"
    if not css.is_file():
        findings.append("missing static/css/studio-control-inline.css")

    partial = ROOT / "templates/siteconfig/feature_control_panel_partial.html"
    if partial.is_file():
        text = partial.read_text(encoding="utf-8", errors="replace")
        if "data-rmc-studio-inline-control" not in text:
            findings.append("feature_control_panel_partial.html missing inline marker")
    else:
        findings.append("missing feature_control_panel_partial.html")

    content = ROOT / "templates/siteconfig/feature_control_panel_content.html"
    if content.is_file():
        text = content.read_text(encoding="utf-8", errors="replace")
        if "studio_inline" not in text:
            findings.append("feature_control_panel_content.html must branch on studio_inline")
        if "data-rmc-studio-inline-control-summary" not in text:
            findings.append("missing compact inline summary strip")
    else:
        findings.append("missing feature_control_panel_content.html")

    views = ROOT / "apps/studio_os/views.py"
    if views.is_file() and 'ctrl_ctx["studio_inline"] = True' not in views.read_text(
        encoding="utf-8"
    ):
        findings.append("studio_shell must set studio_inline on control panel context")

    extrastyle = ROOT / "templates/studio_os/partials/shell_extrastyle.html"
    if extrastyle.is_file() and "studio-control-inline.css" not in extrastyle.read_text(
        encoding="utf-8"
    ):
        findings.append("shell_extrastyle must load studio-control-inline.css")

    if findings:
        print(f"verify_studio_control_inline: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("verify_studio_control_inline: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
