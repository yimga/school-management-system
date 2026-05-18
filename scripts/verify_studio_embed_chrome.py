#!/usr/bin/env python3
"""
Wave 2 gate: Studio embeds use minimal body chrome (no portal_base / CP shell in iframe).

"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_IN_EMBED_TEMPLATES = frozenset(
    {
        "portal_base.html",
        "control_plane_base.html",
        "operator_control_plane_page.html",
    }
)

EMBED_RENDER_RE = re.compile(
    r'render\s*\([^)]*["\']siteconfig/[^"\']+["\']',
    re.MULTILINE,
)


def main() -> int:
    findings: list[str] = []

    subpage = ROOT / "templates/studio_os/studio_subpage_embed.html"
    if subpage.is_file():
        text = subpage.read_text(encoding="utf-8", errors="replace")
        if "portal_base.html" in text:
            findings.append("studio_subpage_embed.html must not extend portal_base")
        if "studio_embed_minimal.html" not in text:
            findings.append("studio_subpage_embed.html must extend studio_embed_minimal")
    else:
        findings.append("missing studio_subpage_embed.html")

    for name in ("studio_embed_minimal.html", "studio_embed_body_shell.html"):
        if not (ROOT / "templates/studio_os" / name).is_file():
            findings.append(f"missing templates/studio_os/{name}")

    embed_py = ROOT / "apps/studio_os/embed_render.py"
    if not embed_py.is_file():
        findings.append("missing apps/studio_os/embed_render.py")

    fc = ROOT / "apps/siteconfig/views_feature_control.py"
    if fc.is_file():
        text = fc.read_text(encoding="utf-8", errors="replace")
        if "render_studio_embed_body" not in text:
            findings.append("feature_control_panel must use render_studio_embed_body for embed=1")

    views_py = ROOT / "apps/siteconfig/views.py"
    if views_py.is_file() and "render_studio_embed_body" not in views_py.read_text(encoding="utf-8"):
        findings.append("theme_colors_page should use render_studio_embed_body when embed=1")

    if findings:
        print(f"verify_studio_embed_chrome: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("verify_studio_embed_chrome: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
