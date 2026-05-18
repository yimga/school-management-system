#!/usr/bin/env python3
"""Wave 5 gate: Studio focus sidebar + control-plane nav group labels are unique."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV_PY = ROOT / "apps/schools/control_plane_nav.py"


def main() -> int:
    findings: list[str] = []

    if not NAV_PY.is_file():
        findings.append("missing apps/schools/control_plane_nav.py")
    else:
        text = NAV_PY.read_text(encoding="utf-8", errors="replace")
        groups = re.findall(r'add_group\(\s*\n?\s*["\']([^"\']+)["\']', text)
        if not groups:
            groups = re.findall(r'add_group\(\s*["\']([^"\']+)["\']', text)
        dup_groups = [g for g in groups if groups.count(g) > 1]
        if dup_groups:
            findings.append(
                f"duplicate CONTROL_PLANE_NAV group labels: {sorted(set(dup_groups))}"
            )

        focus_block = text[text.find("def build_studio_focus_sidebar") :]
        focus_labels = re.findall(
            r'"label": _\("([^"]+)"\)', focus_block.split("def ", 1)[0] if False else focus_block
        )
        if not focus_labels:
            focus_labels = re.findall(r'"label": _\("([^"]+)"\)', focus_block[:4000])
        dup_focus = [l for l in focus_labels if focus_labels.count(l) > 1]
        if dup_focus:
            findings.append(
                f"duplicate studio focus sidebar labels: {sorted(set(dup_focus))}"
            )

        if "def build_studio_focus_sidebar" not in text:
            findings.append("missing build_studio_focus_sidebar")

    sidebar_tpl = ROOT / "templates/partials/control_plane_sidebar_studio_focus.html"
    if sidebar_tpl.is_file():
        body = sidebar_tpl.read_text(encoding="utf-8", errors="replace")
        if "STUDIO_FOCUS_SIDEBAR" not in body:
            findings.append("studio focus sidebar must use STUDIO_FOCUS_SIDEBAR only")
        if "CONTROL_PLANE_NAV" in body:
            findings.append("studio focus sidebar must not render CONTROL_PLANE_NAV")
    else:
        findings.append("missing control_plane_sidebar_studio_focus.html")

    if findings:
        print(f"verify_studio_nav_uniqueness: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("verify_studio_nav_uniqueness: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
