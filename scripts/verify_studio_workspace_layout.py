#!/usr/bin/env python3
"""
Wave 3 gate: Studio OS modes use unified workspace_layout + studio-workspace.css.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODE_CANVASES = (
    "launch_mode_canvas.html",
    "output_mode_canvas.html",
    "automation_mode_canvas.html",
    "control_mode_canvas.html",
)


def main() -> int:
    findings: list[str] = []

    css = ROOT / "static/css/studio-workspace.css"
    if not css.is_file():
        findings.append("missing static/css/studio-workspace.css")
    else:
        body = css.read_text(encoding="utf-8", errors="replace")
        if ".rmc-studio-workspace" not in body:
            findings.append("studio-workspace.css missing .rmc-studio-workspace")

    layout = ROOT / "templates/studio_os/components/workspace_layout.html"
    if not layout.is_file():
        findings.append("missing workspace_layout.html")
    else:
        text = layout.read_text(encoding="utf-8", errors="replace")
        if 'data-rmc-studio-workspace="1"' not in text:
            findings.append("workspace_layout.html missing data-rmc-studio-workspace marker")

    extrastyle = ROOT / "templates/studio_os/partials/shell_extrastyle.html"
    if extrastyle.is_file():
        if "studio-workspace.css" not in extrastyle.read_text(encoding="utf-8"):
            findings.append("shell_extrastyle.html must load studio-workspace.css")

    for name in MODE_CANVASES:
        path = ROOT / "templates/studio_os/partials" / name
        if not path.is_file():
            findings.append(f"missing {name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "workspace_layout.html" not in text and "data-rmc-studio-workspace" not in text:
            findings.append(f"{name} must use workspace_layout or data-rmc-studio-workspace")
        if "public_host_kind != 'manager'" not in text:
            findings.append(
                f"{name} must gate tenant workspace rails with public_host_kind != 'manager'"
            )
        if name == "launch_mode_canvas.html":
            if "public_host_kind == 'manager'" not in text:
                findings.append(
                    "launch_mode_canvas.html must render canvas-only workspace on manager"
                )
            if "launch_canvas.html" not in text:
                findings.append("launch_mode_canvas.html must include launch_canvas.html")

    experience_body = ROOT / "templates/studio_os/partials/studio_experience_mode_body.html"
    experience = ROOT / "templates/studio_os/modes/experience.html"
    exp_sources = []
    if experience.is_file():
        exp_sources.append(experience.read_text(encoding="utf-8", errors="replace"))
    if experience_body.is_file():
        exp_sources.append(experience_body.read_text(encoding="utf-8", errors="replace"))
    if exp_sources and not any("workspace_layout.html" in t for t in exp_sources):
        findings.append(
            "experience mode must use workspace_layout.html (modes/experience or studio_experience_mode_body)"
        )

    workspace_dir = ROOT / "templates/studio_os/partials/workspace"
    for stem in ("launch_rail", "launch_canvas", "output_rail", "output_canvas", "control_rail", "control_canvas"):
        if not (workspace_dir / f"{stem}.html").is_file():
            findings.append(f"missing workspace partial {stem}.html")

    if findings:
        print(f"verify_studio_workspace_layout: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("verify_studio_workspace_layout: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
