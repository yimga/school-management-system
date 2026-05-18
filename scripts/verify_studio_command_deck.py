#!/usr/bin/env python3
"""Wave 7: Studio OS command deck mechanical contract."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    findings: list[str] = []
    partial = ROOT / "templates/studio_os/partials/studio_overview_deck.html"
    if not partial.is_file():
        findings.append("missing studio_overview_deck.html")
    else:
        body = partial.read_text(encoding="utf-8", errors="replace")
        if "data-studio-command-deck" not in body:
            findings.append("overview deck missing data-studio-command-deck")
        if "motion." in body:
            findings.append("overview deck must not use motion.* tags")

    css = ROOT / "static/css/studio-command-deck.css"
    if not css.is_file():
        findings.append("missing studio-command-deck.css")

    shell = ROOT / "templates/studio_os/partials/shell_main_content.html"
    if shell.is_file():
        text = shell.read_text(encoding="utf-8", errors="replace")
        if "studio_overview_deck.html" not in text:
            findings.append("shell_main_content must include studio_overview_deck.html")
    else:
        findings.append("missing shell_main_content.html")

    services = ROOT / "apps/studio_os/services.py"
    if services.is_file():
        text = services.read_text(encoding="utf-8", errors="replace")
        if "def get_studio_overview_deck" not in text:
            findings.append("missing get_studio_overview_deck in services.py")
        if "def get_studio_operator_toolbar" not in text:
            findings.append("missing get_studio_operator_toolbar in services.py")
    else:
        findings.append("missing apps/studio_os/services.py")

    toolbar_tpl = ROOT / "templates/studio_os/partials/studio_operator_toolbar.html"
    if not toolbar_tpl.is_file():
        findings.append("missing studio_operator_toolbar.html")
    elif "data-studio-operator-toolbar" not in toolbar_tpl.read_text(encoding="utf-8"):
        findings.append("operator toolbar missing data-studio-operator-toolbar")

    views = ROOT / "apps/studio_os/views.py"
    if views.is_file() and "def studio_set_operator_school" not in views.read_text(encoding="utf-8"):
        findings.append("missing studio_set_operator_school view")

    if findings:
        print("verify_studio_command_deck:", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_studio_command_deck: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
